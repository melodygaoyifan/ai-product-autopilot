package com.example;

import java.io.File;
import java.io.FileInputStream;
import java.io.ObjectInputStream;
import java.security.cert.X509Certificate;
import javax.crypto.Cipher;
import javax.net.ssl.X509TrustManager;
import javax.xml.parsers.DocumentBuilder;
import javax.xml.parsers.DocumentBuilderFactory;
import org.w3c.dom.Document;

public class Payments {

    // J-SAST-4: path traversal — user input joined straight into a path
    public File receiptFile(String userSuppliedName) {
        return new File("/var/receipts/" + userSuppliedName);
    }

    // J-SAST-5: command injection — user input concatenated into a shell command
    public Process exportLedger(String month) throws Exception {
        return Runtime.getRuntime().exec("sh -c 'ledger-export " + month + "'");
    }

    // J-SAST-6: XXE — parser accepts external entities as configured
    public Document parseInvoice(java.io.InputStream xml) throws Exception {
        DocumentBuilderFactory factory = DocumentBuilderFactory.newInstance();
        DocumentBuilder builder = factory.newDocumentBuilder();
        return builder.parse(xml);
    }

    // J-SAST-7: broken crypto — DES in ECB mode for card data
    public Cipher cardCipher() throws Exception {
        return Cipher.getInstance("DES/ECB/PKCS5Padding");
    }

    // J-SAST-8: trust-all TLS — certificate validation disabled
    public X509TrustManager trustEverything() {
        return new X509TrustManager() {
            public void checkClientTrusted(X509Certificate[] chain, String authType) {}
            public void checkServerTrusted(X509Certificate[] chain, String authType) {}
            public X509Certificate[] getAcceptedIssuers() { return new X509Certificate[0]; }
        };
    }

    // J-SAST-9: insecure deserialization of caller-controlled bytes
    public Object loadSession(String path) throws Exception {
        try (ObjectInputStream in = new ObjectInputStream(new FileInputStream(path))) {
            return in.readObject();
        }
    }

    // J-LINT-4: equals overridden without hashCode
    private final String currency = "USD";

    @Override
    public boolean equals(Object other) {
        return other instanceof Payments
            && ((Payments) other).currency.equals(currency);
    }

    // J-LINT-5: overly broad catch hiding real failures
    public boolean settle(Runnable settlement) {
        try {
            settlement.run();
            return true;
        } catch (Exception e) {
            return false;
        }
    }

    // J-LINT-6: switch over a known set with no default branch
    public int feeBps(String tier) {
        switch (tier) {
            case "standard":
                return 250;
            case "premium":
                return 120;
        }
        return 0;
    }

    // J-MUT-2: negated-conditional mutant survives — the rejection branch
    // is never exercised by any test
    public boolean validateAmount(long cents) {
        if (cents <= 0) {
            return false;
        }
        return cents <= 1_000_000_00L;
    }

    // J-MUT-3: return-value mutant survives — callers ignore the result
    public long roundToUnit(long cents) {
        return (cents / 100) * 100;
    }
}
