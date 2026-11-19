package server;

import java.util.Collection;
import java.util.concurrent.ConcurrentHashMap;

public class SessionManager {
    private final ConcurrentHashMap<Integer, ClientSession> activeSessions = new ConcurrentHashMap<>();

    public void registerUser(int userId, ClientSession session) {
        session.setUserId(userId);
        activeSessions.put(userId, session);
        System.out.println("[SERVER] User registered: ID=" + userId + " (" + session.getUsername() + ")");
    }

    public void removeSession(ClientSession session) {
        if (session.getUserId() != 0) {
            activeSessions.remove(session.getUserId());
            System.out.println("[SERVER] User disconnected: ID=" + session.getUserId());
        }
    }

    public ClientSession getSession(int userId) {
        return activeSessions.get(userId);
    }

    public Collection<ClientSession> getAllSessions() {
        return activeSessions.values();
    }
}