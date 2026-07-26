using System;
using System.Diagnostics;
using System.IO;
using System.Net.Http;
using System.Runtime.Serialization.Formatters.Binary;
using System.Xml;

namespace Seeded
{
    public class Payments
    {
        // N-SAST-4: path traversal — user input joined straight into a path
        public string ReceiptPath(string userSuppliedName)
        {
            return Path.Combine("/var/receipts", userSuppliedName);
        }

        // N-SAST-5: command injection — user input into a shell invocation
        public Process ExportLedger(string month)
        {
            return Process.Start("sh", "-c \"ledger-export " + month + "\"");
        }

        // N-SAST-6: XXE — resolver left enabled on the XML reader
        public XmlDocument ParseInvoice(Stream xml)
        {
            var doc = new XmlDocument();
            doc.XmlResolver = new XmlUrlResolver();
            doc.Load(xml);
            return doc;
        }

        // N-SAST-7: insecure deserialization (BinaryFormatter on caller bytes)
        public object LoadSession(Stream data)
        {
            var formatter = new BinaryFormatter();
            return formatter.Deserialize(data);
        }

        // N-SAST-8: TLS validation disabled
        public HttpClient TrustEverything()
        {
            var handler = new HttpClientHandler
            {
                ServerCertificateCustomValidationCallback = (m, c, ch, e) => true,
            };
            return new HttpClient(handler);
        }

        // N-LINT-3: unreachable code after return
        public int FeeBps(string tier)
        {
            return tier == "premium" ? 120 : 250;
            Console.WriteLine("unreachable");
        }

        // N-MUT-2: negated-conditional mutant survives — rejection untested
        public bool ValidateAmount(long cents)
        {
            if (cents <= 0)
            {
                return false;
            }
            return cents <= 1_000_000_00L;
        }

        // N-MUT-3: return-value mutant survives — callers ignore the result
        public long RoundToUnit(long cents)
        {
            return (cents / 100) * 100;
        }
    }
}
