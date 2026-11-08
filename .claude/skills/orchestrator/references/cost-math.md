# Cost math for a long session

Use your provider's real prices; the shape matters more than the numbers.

- **Per message:** context tokens × cache-read price + new input × input price + output × output price.
  Every message re-reads the whole context, so a big session costs mostly in cache reads.
- **Sawtooth:** after a compaction a session restarts at B tokens (80-120k measured) and grows by g
  per turn (about 1.5k measured) until it compacts again at T. Average context ≈ (B + T) / 2.
- **Per-turn cost, in input-token units:** 0.05(B + T) for cache reads at a tenth of the input
  price, plus 2g for cache writes, plus C/N for the compaction itself, where N = (T − B)/g turns per
  cycle and C ≈ 0.1T + 75k (the summary) + 2B (rebuilding the cache).
- **The threshold:** the pure-cost optimum is where (T − B)² = g·C/0.05, about 200k with the measured
  B and g. Per turn that gives roughly 24k units at 200k, 30k at 400k, 35k at 500k and 47k at 750k:
  500k is about a quarter cheaper than 750k. A larger context buys quality, so the threshold is a
  choice between the two, not the optimum alone.
- **Measured split** (one fleet, all sessions, one day): cache reads 71%, cache writes 22%, output 7%.
- **The bigger lever is turns.** One session made about 1,500 turns in a day; most were checks that
  found nothing. Batch tool calls, wake on events, and give workers the bounded work.
- **Delegation:** the same worker tokens cost several times less on a mid-tier model than on the
  top one, and an order of magnitude less on a cheap tier. The orchestration tax (messages spent
  launching and reviewing, times the average context) was a few per day and small next to that.
