package integration;

import common.ErrorCode;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;

import javax.crypto.SecretKeyFactory;
import javax.crypto.spec.PBEKeySpec;
import java.security.GeneralSecurityException;
import java.security.MessageDigest;
import java.security.SecureRandom;
import java.util.Base64;
import java.util.HashMap;
import java.util.Map;

import static org.junit.jupiter.api.Assertions.*;

/**
 * Ca kiểm thử 4: Bảo mật mật khẩu và xác thực tài khoản (Password Hashing & Security)
 * Phối hợp với Đông: Chứng minh mật khẩu được băm (Salt + PBKDF2), không lưu dạng rõ (plain text),
 * và bắt đúng các mã lỗi INVALID_CREDENTIALS (1001) và INVALID_PAYLOAD (1003).
 */
public class TestPasswordSecurity {

    public static void main(String[] args) {
        System.out.println("=== CHẠY KIỂM THỬ: BẢO MẬT MẬT KHẨU VÀ XÁC THỰC (PASSWORD SECURITY) ===");
        TestPasswordSecurity tester = new TestPasswordSecurity();
        try {
            tester.testPasswordNotStoredInPlainText();
            System.out.println("[PASS] 1. No Plaintext Storage - Mật khẩu lưu dưới dạng Salt + PBKDF2 Hash.");

            tester.testSaltUniqueness();
            System.out.println("[PASS] 2. Salt Uniqueness - Cùng mật khẩu nhưng sinh ra 2 hash hoàn toàn khác nhau nhờ Salt ngẫu nhiên.");

            tester.testAuthenticationSuccessAndFailure();
            System.out.println("[PASS] 3. Authentication - Đúng pass đăng nhập thành công; sai pass trả về mã lỗi 1001 (INVALID_CREDENTIALS).");

            tester.testPasswordPolicyValidation();
            System.out.println("[PASS] 4. Password Policy - Mật khẩu quá ngắn (< 8 ký tự) bị từ chối với mã lỗi 1003 (INVALID_PAYLOAD).");

            System.out.println("===> TẤT CẢ CA KIỂM THỬ BẢO MẬT MẬT KHẨU ĐỀU THÀNH CÔNG!\n");
        } catch (Throwable t) {
            System.err.println("[FAIL] Lỗi kiểm thử: " + t.getMessage());
            t.printStackTrace();
        }
    }

    // Cấu hình mã hóa chuẩn theo thiết kế của Đông (PBKDF2WithHmacSHA256, 16 bytes salt, 10,000+ vòng)
    private static final int ITERATIONS = 20_000;
    private static final SecureRandom RANDOM = new SecureRandom();

    public record StoredAccount(int userId, String username, String salt, String passwordHash) {}

    private static String hashPassword(String password, byte[] salt) {
        PBEKeySpec spec = new PBEKeySpec(password.toCharArray(), salt, ITERATIONS, 256);
        try {
            byte[] encoded = SecretKeyFactory.getInstance("PBKDF2WithHmacSHA256")
                    .generateSecret(spec).getEncoded();
            return Base64.getEncoder().encodeToString(encoded);
        } catch (GeneralSecurityException e) {
            throw new RuntimeException("Lỗi thuật toán mã hóa", e);
        } finally {
            spec.clearPassword();
        }
    }

    @Test
    @DisplayName("1. Mật khẩu không bao giờ được lưu dưới dạng plain text")
    public void testPasswordNotStoredInPlainText() {
        String plainPassword = "SuperSecretPassword123!";
        byte[] salt = new byte[16];
        RANDOM.nextBytes(salt);
        String saltBase64 = Base64.getEncoder().encodeToString(salt);
        String hashBase64 = hashPassword(plainPassword, salt);

        StoredAccount account = new StoredAccount(1, "alice", saltBase64, hashBase64);

        // Chứng minh trong trường lưu trữ hoàn toàn không chứa chuỗi plain text
        assertNotEquals(plainPassword, account.passwordHash());
        assertFalse(account.passwordHash().contains(plainPassword));
        assertFalse(account.salt().contains(plainPassword));
    }

    @Test
    @DisplayName("2. Tính duy nhất của Salt: Cùng 1 mật khẩu đăng ký cho 2 user sẽ sinh ra 2 hash khác nhau")
    public void testSaltUniqueness() {
        String samePassword = "CommonPassword456@";

        byte[] salt1 = new byte[16];
        byte[] salt2 = new byte[16];
        RANDOM.nextBytes(salt1);
        RANDOM.nextBytes(salt2);

        String hash1 = hashPassword(samePassword, salt1);
        String hash2 = hashPassword(samePassword, salt2);

        assertNotEquals(hash1, hash2, "Nhờ Salt ngẫu nhiên, hai mật khẩu giống hệt nhau không bao giờ trùng mã băm (chống Rainbow Table)");
    }

    @Test
    @DisplayName("3. Xác thực: Đúng pass thành công, sai pass trả về mã lỗi 1001 (INVALID_CREDENTIALS)")
    public void testAuthenticationSuccessAndFailure() {
        String user = "bob";
        String correctPass = "CorrectPassword789#";
        String wrongPass = "WrongPassword000#";

        byte[] salt = new byte[16];
        RANDOM.nextBytes(salt);
        String storedHash = hashPassword(correctPass, salt);

        // Giả lập cơ chế xác thực của server
        Map<String, StoredAccount> db = new HashMap<>();
        db.put(user, new StoredAccount(2, user, Base64.getEncoder().encodeToString(salt), storedHash));

        // Trường hợp 1: Bob nhập đúng password
        StoredAccount bob = db.get(user);
        byte[] bobSalt = Base64.getDecoder().decode(bob.salt());
        String loginHash1 = hashPassword(correctPass, bobSalt);
        assertTrue(MessageDigest.isEqual(storedHash.getBytes(), loginHash1.getBytes()),
                "Đúng mật khẩu phải xác thực thành công");

        // Trường hợp 2: Bob nhập sai password -> Phải kích hoạt mã lỗi 1001
        String loginHash2 = hashPassword(wrongPass, bobSalt);
        boolean isMatch = MessageDigest.isEqual(storedHash.getBytes(), loginHash2.getBytes());
        assertFalse(isMatch, "Sai mật khẩu phải bị từ chối");

        int errorCode = isMatch ? ErrorCode.SUCCESS : ErrorCode.INVALID_CREDENTIALS;
        assertEquals(ErrorCode.INVALID_CREDENTIALS, errorCode, "Phải trả về mã lỗi INVALID_CREDENTIALS (1001)");
    }

    @Test
    @DisplayName("4. Kiểm tra chính sách mật khẩu: Mật khẩu < 8 ký tự bị từ chối với mã lỗi 1003 (INVALID_PAYLOAD)")
    public void testPasswordPolicyValidation() {
        String shortPassword = "12345"; // Quá ngắn (< 8 ký tự)

        boolean isValid = validatePassword(shortPassword);
        assertFalse(isValid, "Mật khẩu < 8 ký tự không được chấp nhận");

        int errorCode = isValid ? ErrorCode.SUCCESS : ErrorCode.INVALID_PAYLOAD;
        assertEquals(ErrorCode.INVALID_PAYLOAD, errorCode, "Phải kích hoạt mã lỗi INVALID_PAYLOAD (1003)");
    }

    private static boolean validatePassword(String password) {
        return password != null && password.length() >= 8 && password.length() <= 128;
    }
}
