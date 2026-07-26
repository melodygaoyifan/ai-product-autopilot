using Seeded;
using Xunit;

namespace Seeded.Tests
{
    public class AppTests
    {
        // N-TEST-1: assertion-free test — passes while verifying nothing
        [Fact]
        public void ParseCountRuns()
        {
            new App().ParseCount("7");
        }

        // N-MUT-1 counterpart: only the happy path is asserted; the >=100
        // boundary and the 20% branch never are, so boundary mutants survive
        [Fact]
        public void SmallOrderDiscount()
        {
            Assert.Equal(5, new App().DiscountPercent(1));
        }
    }
}
