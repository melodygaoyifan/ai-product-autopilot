using System;
using System.Data.SqlClient;
using System.Security.Cryptography;
using System.Collections.Generic;   // N-LINT-1: unused using

namespace Seeded
{
    public class App
    {
        // N-SAST-2: hardcoded connection secret
        private const string ConnectionString =
            "Server=db;Database=app;User Id=sa;Password=hunter2;";

        // N-SAST-1: SQL built by string concatenation from caller input
        public SqlCommand FindUser(SqlConnection conn, string name)
        {
            var cmd = conn.CreateCommand();
            cmd.CommandText = "SELECT * FROM users WHERE name = '" + name + "'";
            return cmd;
        }

        // N-SAST-3: broken crypto — MD5 for a password digest
        public static byte[] DigestPassword(byte[] password)
        {
            using var md5 = MD5.Create();
            return md5.ComputeHash(password);
        }

        // N-LINT-2: swallowed exception (empty catch)
        public int ParseCount(string raw)
        {
            try
            {
                return int.Parse(raw);
            }
            catch (FormatException)
            {
            }
            return 0;
        }

        // N-MUT-1: boundary no test asserts — the >= mutant survives
        public int DiscountPercent(int quantity)
        {
            if (quantity >= 100)
            {
                return 20;
            }
            return 5;
        }
    }
}
