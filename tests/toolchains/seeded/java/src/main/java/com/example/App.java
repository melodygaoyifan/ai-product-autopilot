package com.example;

import java.sql.Connection;
import java.sql.ResultSet;
import java.sql.Statement;
import java.util.List;   // J-LINT-1: unused import

public class App {

    // J-SAST-2: hardcoded credential
    private static final String DB_PASSWORD = "hunter2";

    // J-SAST-1: SQL built by string concatenation from caller input
    public ResultSet findUser(Connection conn, String name) throws Exception {
        Statement st = conn.createStatement();
        return st.executeQuery("SELECT * FROM users WHERE name = '" + name + "'");
    }

    // J-LINT-2: string comparison with ==
    public boolean isAdmin(String role) {
        return role == "admin";
    }

    // J-LINT-3: swallowed exception (empty catch)
    public int parseCount(String raw) {
        try {
            return Integer.parseInt(raw);
        } catch (NumberFormatException e) {
        }
        return 0;
    }

    // J-SAST-3: predictable randomness used for a token
    public String sessionToken() {
        java.util.Random r = new java.util.Random();
        return Long.toHexString(r.nextLong());
    }

    // J-MUT-1: branch no test exercises — a surviving mutant on the boundary
    public int discountPercent(int quantity) {
        if (quantity >= 100) {
            return 20;
        }
        return 5;
    }
}
