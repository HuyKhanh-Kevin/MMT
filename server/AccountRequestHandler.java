package server;

import common.*;
import common.payload.*;

import java.io.IOException;
import java.net.InetAddress;
import java.net.InetSocketAddress;
import java.util.UUID;
import java.util.logging.Level;
import java.util.logging.Logger;

/** Account protocol entry point shared by the tracker and other server transports.
 * Connection IDs and source addresses must come from the server, never from JSON.
 * This class does not own sockets, threads, presence delivery or the expiry timer.
 */
public final class AccountRequestHandler {
    private static final Logger LOG = Logger.getLogger(AccountRequestHandler.class.getName());
    private final AccountStore accounts;
    private final SessionRegistry sessions;
    private final OnlineDirectory directory;

    public AccountRequestHandler(AccountStore accounts, SessionRegistry sessions, OnlineDirectory directory) {
        this.accounts = accounts;
        this.sessions = sessions;
        this.directory = directory;
    }

    public Packet handleTcp(UUID connection, InetAddress sourceIP, Packet request) throws IOException {
        try {
            validateHeader(request);
            return tcp(connection, sourceIP, request);
        } catch (AccountException e) {
            return error(request, e.code(), e.getMessage());
        } catch (IOException | IllegalArgumentException e) {
            return error(request, ErrorCode.INVALID_PAYLOAD, "INVALID_PAYLOAD");
        }
    }

    /** A valid heartbeat has no response; discovery and rejected requests return a packet. */
    public Packet handleUdp(Packet request, InetSocketAddress source) throws IOException {
        try {
            validateHeader(request);
            int type = request.getHeader().getMessageType();
            int sender = request.getHeader().getSenderID();
            if (type == Integer.decode(MessageType.HEARTBEAT)) {
                Heartbeat heartbeat = JsonPayloadCodec.decode(request.getPayload(), Heartbeat.class);
                sessions.heartbeat(heartbeat.getSessionID(), sender, heartbeat.getHeartbeatSeq(), source);
                return null;
            }
            if (type == Integer.decode(MessageType.USER_LIST_REQUEST)) {
                UserListRequest list = JsonPayloadCodec.decode(request.getPayload(), UserListRequest.class);
                // Validate even subsequent/cached pages: a cursor does not authorize its owner.
                var users = sessions.discover(list.getSessionID(), sender, source);
                return reply(request, MessageType.USER_LIST_RESPONSE, sender,
                        directory.page(list.getSessionID(), list.getCursor(), users));
            }
            throw invalid("UNSUPPORTED_UDP_MESSAGE");
        } catch (AccountException e) {
            return error(request, e.code(), e.getMessage());
        } catch (IOException | IllegalArgumentException e) {
            return error(request, ErrorCode.INVALID_PAYLOAD, "INVALID_PAYLOAD");
        }
    }

    private Packet tcp(UUID connection, InetAddress sourceIP, Packet request)
            throws IOException, AccountException {
        int type = request.getHeader().getMessageType();
        int sender = request.getHeader().getSenderID();
        if (type == Integer.decode(MessageType.SIGNUP_REQUEST)) {
            if (sender != 0 || sessions.hasSession(connection)) throw invalid("ALREADY_AUTHENTICATED");
            SignupRequest signup = JsonPayloadCodec.decode(request.getPayload(), SignupRequest.class);
            SignupResponse response;
            try {
                accounts.signup(signup.username(), signup.password());
                response = new SignupResponse("success");
            } catch (AccountException e) {
                response = new SignupResponse("failed", e.getMessage());
            } catch (IOException e) {
                LOG.log(Level.WARNING, "Account persistence failed", e);
                response = new SignupResponse("failed", "ACCOUNT_STORE_UNAVAILABLE");
            }
            return reply(request, MessageType.SIGNUP_RESPONSE, 0, response);
        }
        if (type == Integer.decode(MessageType.LOGIN_REQUEST)) {
            if (sender != 0 || sessions.hasSession(connection)) throw invalid("ALREADY_AUTHENTICATED");
            LoginRequest login = JsonPayloadCodec.decode(request.getPayload(), LoginRequest.class);
            LoginResponse response;
            try {
                if (login.getTcpPort() < 1 || login.getTcpPort() > 65535
                        || login.getFileUdpPort() < 1 || login.getFileUdpPort() > 65535) throw invalid("INVALID_PORT");
                AccountStore.Account account = accounts.authenticate(login.getUsername(), login.getPassword());
                var session = sessions.login(account, sourceIP, login.getTcpPort(), login.getFileUdpPort(), connection);
                response = new LoginResponse(true, session.sessionID(), account.userID(), null);
            } catch (AccountException e) {
                response = new LoginResponse(false, null, 0, e.getMessage());
            }
            return reply(request, MessageType.LOGIN_RESPONSE, response.isStatus() ? response.getUserID() : 0, response);
        }
        if (type == Integer.decode(MessageType.LOGOUT_REQUEST)) {
            LogoutRequest logout = JsonPayloadCodec.decode(request.getPayload(), LogoutRequest.class);
            sessions.logout(logout.getSessionID(), sender, connection);
            return reply(request, MessageType.LOGOUT_RESPONSE, sender, new LogoutResponse("success"));
        }
        throw invalid("UNSUPPORTED_TCP_MESSAGE");
    }

    private static void validateHeader(Packet request) throws AccountException {
        PacketHeader header = request.getHeader();
        if (header.getFlags() != 0 || header.getStreamID() != 0
                || header.getSequenceNumber() == 0 || header.getReceiverID() != 0) {
            throw invalid("INVALID_CONTROL_HEADER");
        }
    }

    private static Packet reply(Packet request, String type, int receiver, Object value) throws IOException {
        return ControlPackets.create(type, request.getHeader().getSequenceNumber(), 0, receiver, value);
    }

    private static Packet error(Packet request, int code, String reason) throws IOException {
        return reply(request, MessageType.ERROR, request.getHeader().getSenderID(),
                new ErrorPayload(code, reason, Integer.toUnsignedLong(request.getHeader().getStreamID()),
                        Integer.toUnsignedLong(request.getHeader().getSequenceNumber())));
    }

    private static AccountException invalid(String reason) {
        return new AccountException(ErrorCode.INVALID_PAYLOAD, reason);
    }
}
