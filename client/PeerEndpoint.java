package client;

import java.net.InetSocketAddress;

/** Discovered addresses for the file-transfer module; carries no session secret. */
public record PeerEndpoint(long userID, String username,
                           InetSocketAddress tcp, InetSocketAddress fileUDP) {}
