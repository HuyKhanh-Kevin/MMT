package server;

import com.fasterxml.jackson.core.type.TypeReference;
import com.fasterxml.jackson.databind.json.JsonMapper;
import common.ErrorCode;

import javax.crypto.SecretKeyFactory;
import javax.crypto.spec.PBEKeySpec;
import java.io.IOException;
import java.nio.file.*;
import java.security.GeneralSecurityException;
import java.security.MessageDigest;
import java.security.SecureRandom;
import java.util.*;

/** Persistent accounts; active sessions are deliberately kept out of this file. */
public final class AccountStore {
    private static final int ITERATIONS = 210_000;
    private static final SecureRandom RANDOM = new SecureRandom();
    private final JsonMapper mapper = JsonMapper.builder().build();
    private final Path file;
    private final Map<String, StoredAccount> accounts = new HashMap<>();
    private int nextID = 1;

    public record Account(int userID, String username) {}
    public record StoredAccount(int userID, String username, String salt,
                                String passwordHash, int iterations) {}

    public AccountStore(Path file) throws IOException {
        this.file = file.toAbsolutePath();
        if (Files.exists(this.file)) {
            List<StoredAccount> stored = mapper.readValue(this.file.toFile(), new TypeReference<>() {});
            Set<Integer> ids = new HashSet<>();
            for (StoredAccount entry : stored) {
                if (entry.userID() < 1 || entry.userID() == Integer.MAX_VALUE
                        || !validUsername(entry.username()) || !ids.add(entry.userID())
                        || accounts.putIfAbsent(entry.username(), entry) != null
                        || entry.iterations() < 1 || entry.iterations() > 2_000_000) {
                    throw new IOException("Invalid account database");
                }
                try {
                    if (Base64.getDecoder().decode(entry.salt()).length != 16
                            || Base64.getDecoder().decode(entry.passwordHash()).length != 32) {
                        throw new IllegalArgumentException("Invalid password hash");
                    }
                } catch (IllegalArgumentException e) {
                    throw new IOException("Invalid account database", e);
                }
                nextID = Math.max(nextID, entry.userID() + 1);
            }
        }
    }

    public Account signup(String username, String password) throws AccountException, IOException {
        validateCredentials(username, password);
        synchronized (this) {
            if (accounts.containsKey(username)) throw taken();
        }
        byte[] salt = new byte[16];
        RANDOM.nextBytes(salt);
        String hash = Base64.getEncoder().encodeToString(hash(password, salt, ITERATIONS));
        synchronized (this) {
            // Recheck after hashing: concurrent signups must not create two copies.
            if (accounts.containsKey(username)) throw taken();
            if (nextID == Integer.MAX_VALUE) throw new IOException("User ID space exhausted");
            StoredAccount entry = new StoredAccount(nextID, username,
                    Base64.getEncoder().encodeToString(salt), hash, ITERATIONS);
            List<StoredAccount> updated = new ArrayList<>(accounts.values());
            updated.add(entry);
            updated.sort(Comparator.comparingInt(StoredAccount::userID));
            persist(updated);
            accounts.put(username, entry);
            nextID++;
            return new Account(entry.userID(), username);
        }
    }

    public Account authenticate(String username, String password) throws AccountException {
        validateCredentials(username, password);
        StoredAccount entry;
        synchronized (this) { entry = accounts.get(username); }
        if (entry == null || !MessageDigest.isEqual(
                Base64.getDecoder().decode(entry.passwordHash()),
                hash(password, Base64.getDecoder().decode(entry.salt()), entry.iterations()))) {
            throw new AccountException(ErrorCode.INVALID_CREDENTIALS, "INVALID_CREDENTIALS");
        }
        return new Account(entry.userID(), entry.username());
    }

    private void persist(List<StoredAccount> updated) throws IOException {
        Files.createDirectories(file.getParent());
        Path temporary = Files.createTempFile(file.getParent(), "accounts-", ".tmp");
        try {
            mapper.writerWithDefaultPrettyPrinter().writeValue(temporary.toFile(), updated);
            try {
                Files.move(temporary, file, StandardCopyOption.REPLACE_EXISTING,
                        StandardCopyOption.ATOMIC_MOVE);
            } catch (AtomicMoveNotSupportedException e) {
                Files.move(temporary, file, StandardCopyOption.REPLACE_EXISTING);
            }
        } finally {
            Files.deleteIfExists(temporary);
        }
    }

    private static byte[] hash(String password, byte[] salt, int iterations) {
        PBEKeySpec spec = new PBEKeySpec(password.toCharArray(), salt, iterations, 256);
        try {
            return SecretKeyFactory.getInstance("PBKDF2WithHmacSHA256").generateSecret(spec).getEncoded();
        } catch (GeneralSecurityException e) {
            throw new IllegalStateException("PBKDF2 unavailable", e);
        } finally {
            spec.clearPassword();
        }
    }

    public static boolean validUsername(String username) {
        return username != null && username.matches("[A-Za-z0-9_]{1,32}");
    }

    public static void validateCredentials(String username, String password) throws AccountException {
        if (!validUsername(username) || password == null || !password.matches("[\\x20-\\x7E]{8,128}")) {
            throw new AccountException(ErrorCode.INVALID_PAYLOAD, "INVALID_PAYLOAD");
        }
    }

    private static AccountException taken() {
        return new AccountException(ErrorCode.USERNAME_TAKEN, "USERNAME_TAKEN");
    }
}
