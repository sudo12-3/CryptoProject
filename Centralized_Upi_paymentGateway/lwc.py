from __future__ import print_function

class SpeckCipher(object):
    def encrypt_round(self, x, y, k):
        """Complete one round of enc"""
        rs_x = ((x << (self.word_size - self.alpha_shift)) + (x >> self.alpha_shift)) & self.mod_mask
        add_sxy = (rs_x + y) & self.mod_mask
        new_x = k ^ add_sxy
        ls_y = ((y >> (self.word_size - self.beta_shift)) + (y << self.beta_shift)) & self.mod_mask
        new_y = new_x ^ ls_y
        return new_x, new_y

    def decrypt_round(self, x, y, k):
        """Complete one round of inverse"""
        xor_xy = x ^ y
        new_y = ((xor_xy << (self.word_size - self.beta_shift)) + (xor_xy >> self.beta_shift)) & self.mod_mask
        xor_xk = x ^ k
        msub = ((xor_xk - new_y) + self.mod_mask_sub) % self.mod_mask_sub
        new_x = ((msub >> (self.word_size - self.alpha_shift)) + (msub << self.alpha_shift)) & self.mod_mask
        return new_x, new_y

    def __init__(self, key):
        self.block_size = 64     
        self.key_size = 128      
        self.rounds = 27         
        self.word_size = self.block_size >> 1 
        self.mod_mask = (2 ** self.word_size) - 1
        self.mod_mask_sub = (2 ** self.word_size)
        self.beta_shift = 3
        self.alpha_shift = 8
        try:
            self.key = key & ((2 ** self.key_size) - 1)
        except (ValueError, TypeError):
            raise ValueError("Invalid Key Value! Please provide key as int.")

        # Generate key schedule.
        self.key_schedule = [self.key & self.mod_mask]
        l_schedule = [(self.key >> (x * self.word_size)) & self.mod_mask 
                      for x in range(1, self.key_size // self.word_size)]
        for x in range(self.rounds - 1):
            new_l_k = self.encrypt_round(l_schedule[x], self.key_schedule[x], x)
            l_schedule.append(new_l_k[0])
            self.key_schedule.append(new_l_k[1])

    def encrypt(self, plaintext):
        try:
            b = (plaintext >> self.word_size) & self.mod_mask
            a = plaintext & self.mod_mask
        except TypeError:
            raise ValueError("Invalid plaintext! Please provide plaintext as int.")

        b, a = self.encrypt_function(b, a)
        ciphertext = (b << self.word_size) + a
        return ciphertext

    def decrypt(self, ciphertext):
        # Expect ciphertext as an int.
        try:
            b = (ciphertext >> self.word_size) & self.mod_mask
            a = ciphertext & self.mod_mask
        except TypeError:
            raise ValueError("Invalid ciphertext! Please provide ciphertext as int.")

        b, a = self.decrypt_function(b, a)
        plaintext = (b << self.word_size) + a
        return plaintext

    def encrypt_function(self, upper_word, lower_word):
        x = upper_word
        y = lower_word
        for k in self.key_schedule:
            rs_x = ((x << (self.word_size - self.alpha_shift)) + (x >> self.alpha_shift)) & self.mod_mask
            add_sxy = (rs_x + y) & self.mod_mask
            x = k ^ add_sxy
            ls_y = ((y >> (self.word_size - self.beta_shift)) + (y << self.beta_shift)) & self.mod_mask
            y = x ^ ls_y
        return x, y

    def decrypt_function(self, upper_word, lower_word):
        x = upper_word
        y = lower_word
        for k in reversed(self.key_schedule):
            xor_xy = x ^ y
            y = ((xor_xy << (self.word_size - self.beta_shift)) + (xor_xy >> self.beta_shift)) & self.mod_mask
            xor_xk = x ^ k
            msub = ((xor_xk - y) + self.mod_mask_sub) % self.mod_mask_sub
            x = ((msub >> (self.word_size - self.alpha_shift)) + (msub << self.alpha_shift)) & self.mod_mask
        return x, y
if __name__ == "__main__":
    cipher = SpeckCipher(0x12345678901234567890123456789012)
    g = int(input("Enter MID (in hex, e.g. 0x1234abcd): "), 16)
    encrypted = cipher.encrypt(g)
    print("Encrypted MID:", hex(encrypted))
    decrypted = cipher.decrypt(encrypted)
    print(hex(decrypted))
