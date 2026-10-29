package server;

import common.ErrorCode;
import common.JsonPayloadCodec;
import common.payload.UserInfo;
import common.payload.UserListResponse;

import java.io.IOException;
import java.time.Duration;
import java.util.*;
import java.util.function.LongSupplier;

/** Bounded, session-bound snapshots give stable pages under concurrent presence changes. */
public final class OnlineDirectory {
    private static final long TTL = Duration.ofSeconds(30).toNanos();
    private final LongSupplier nanoTime;
    private final LinkedHashMap<String, Snapshot> snapshots = new LinkedHashMap<>();
    private record Snapshot(String owner, List<UserListResponse> pages, long created) {}

    public OnlineDirectory() { this(System::nanoTime); }
    public OnlineDirectory(LongSupplier nanoTime) { this.nanoTime = nanoTime; }

    public synchronized UserListResponse page(String owner, String cursor, List<UserInfo> users)
            throws IOException, AccountException {
        cleanup();
        if (cursor != null) {
            if (cursor.length() > 64) throw invalidCursor();
            int separator = cursor.lastIndexOf(':');
            if (separator < 0) throw invalidCursor();
            Snapshot snapshot = snapshots.get(cursor.substring(0, separator));
            try {
                int index = Integer.parseInt(cursor.substring(separator + 1));
                if (snapshot == null || !snapshot.owner().equals(owner)
                        || index < 1 || index >= snapshot.pages().size()) throw invalidCursor();
                return snapshot.pages().get(index);
            } catch (NumberFormatException e) {
                throw invalidCursor();
            }
        }

        String id = UUID.randomUUID().toString();
        List<List<UserInfo>> groups = new ArrayList<>();
        List<UserInfo> group = new ArrayList<>();
        for (UserInfo user : users) {
            List<UserInfo> candidate = new ArrayList<>(group);
            candidate.add(user);
            // Reserve the longest possible next_cursor before committing this page.
            if (!fits(new UserListResponse(candidate, id + ":2147483647"))) {
                if (group.isEmpty()) throw new IOException("A peer entry exceeds the JSON payload limit");
                groups.add(List.copyOf(group));
                group.clear();
            }
            group.add(user);
        }
        if (!group.isEmpty() || groups.isEmpty()) groups.add(List.copyOf(group));
        List<UserListResponse> pages = new ArrayList<>();
        for (int i = 0; i < groups.size(); i++) {
            UserListResponse page = new UserListResponse(groups.get(i), i + 1 < groups.size() ? id + ":" + (i + 1) : null);
            JsonPayloadCodec.encode(page);
            pages.add(page);
        }
        if (pages.size() > 1) {
            // At most four live snapshots per session; a new list can supersede the oldest.
            while (snapshots.values().stream().filter(s -> s.owner().equals(owner)).count() >= 4) {
                String oldest = snapshots.entrySet().stream().filter(e -> e.getValue().owner().equals(owner))
                        .findFirst().orElseThrow().getKey();
                snapshots.remove(oldest);
            }
            snapshots.put(id, new Snapshot(owner, List.copyOf(pages), nanoTime.getAsLong()));
        }
        return pages.get(0);
    }

    public synchronized void cleanup() {
        snapshots.values().removeIf(s -> nanoTime.getAsLong() - s.created() >= TTL);
    }

    private static boolean fits(UserListResponse page) {
        try { JsonPayloadCodec.encode(page); return true; }
        catch (IOException e) { return false; }
    }
    private static AccountException invalidCursor() {
        return new AccountException(ErrorCode.INVALID_PAYLOAD, "INVALID_CURSOR");
    }
}
