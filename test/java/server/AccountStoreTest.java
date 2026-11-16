package test.java.server;

import common.ErrorCode;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

import java.nio.file.Files;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.*;

import static org.junit.jupiter.api.Assertions.*;

class AccountStoreTest {
    @TempDir Path temp;

    @Test void signupPersistsStableIdentityWithoutPlaintextPassword() throws Exception {
        Path file = temp.resolve("accounts.json");
        AccountStore store = new AccountStore(file);
        AccountStore.Account alice = store.signup("alice", "password123");
        store.signup("bob", "password123");
        String database = Files.readString(file);
        assertFalse(database.contains("password123"));
        assertTrue(database.contains("passwordHash"));
        AccountStore reopened = new AccountStore(file);
        assertEquals(alice, reopened.authenticate("alice", "password123"));
        assertTrue(reopened.signup("charlie", "password123").userID() > alice.userID());
    }

    @Test void duplicateAndWrongPasswordAreRejected() throws Exception {
        AccountStore store = new AccountStore(temp.resolve("accounts.json"));
        store.signup("alice", "password123");
        assertEquals(ErrorCode.USERNAME_TAKEN,
                assertThrows(AccountException.class, () -> store.signup("alice", "otherPassword")).code());
        assertEquals(ErrorCode.INVALID_CREDENTIALS,
                assertThrows(AccountException.class, () -> store.authenticate("alice", "wrongpass")).code());
        assertEquals(ErrorCode.INVALID_CREDENTIALS,
                assertThrows(AccountException.class, () -> store.authenticate("missing", "wrongpass")).code());
    }

    @Test void validatesCredentialBoundsAndUsesCaseSensitiveNames() throws Exception {
        AccountStore store = new AccountStore(temp.resolve("accounts.json"));
        for (String name : List.of("", "a b", "a/b", "a".repeat(33), "tên")) {
            assertThrows(AccountException.class, () -> store.signup(name, "password123"));
        }
        assertThrows(AccountException.class, () -> store.signup("alice", "short"));
        assertThrows(AccountException.class, () -> store.signup("alice", "p".repeat(129)));
        assertNotEquals(store.signup("Alice", "password123").userID(),
                store.signup("alice", "password123").userID());
    }

    @Test void concurrentSignupCreatesExactlyOneAccount() throws Exception {
        AccountStore store = new AccountStore(temp.resolve("accounts.json"));
        ExecutorService pool = Executors.newFixedThreadPool(6);
        CountDownLatch start = new CountDownLatch(1);
        try {
            List<Future<Boolean>> attempts = new ArrayList<>();
            for (int i = 0; i < 6; i++) attempts.add(pool.submit(() -> {
                start.await();
                try { store.signup("alice", "password123"); return true; }
                catch (AccountException e) { assertEquals(ErrorCode.USERNAME_TAKEN, e.code()); return false; }
            }));
            start.countDown();
            int successes = 0;
            for (Future<Boolean> attempt : attempts) if (attempt.get(10, TimeUnit.SECONDS)) successes++;
            assertEquals(1, successes);
            assertEquals(1, new AccountStore(temp.resolve("accounts.json")).authenticate("alice", "password123").userID());
        } finally { pool.shutdownNow(); }
    }

    @Test void failedSaveDoesNotPublishAnAccount() throws Exception {
        Path parent = temp.resolve("blocked");
        AccountStore store = new AccountStore(parent.resolve("accounts.json"));
        Files.writeString(parent, "This is a file, so it cannot contain accounts.json");
        assertThrows(java.io.IOException.class, () -> store.signup("alice", "password123"));
        assertEquals(ErrorCode.INVALID_CREDENTIALS,
                assertThrows(AccountException.class, () -> store.authenticate("alice", "password123")).code());
    }
}
