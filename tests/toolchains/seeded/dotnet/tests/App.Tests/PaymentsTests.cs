using Seeded;
using Xunit;

namespace Seeded.Tests
{
    public class PaymentsTests
    {
        // N-TEST-2: only the happy path is asserted, so N-MUT-2's rejection
        // branch (cents <= 0) and the upper bound both survive
        [Fact]
        public void AcceptsAPositiveAmount()
        {
            Assert.True(new Payments().ValidateAmount(500));
        }

        [Fact]
        public void RoundsDownToUnit()
        {
            Assert.Equal(500, new Payments().RoundToUnit(567));
        }
    }
}
