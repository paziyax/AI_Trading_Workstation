-- FinAlly seed data.
--
-- Executed by Database.initialize() after schema.sql. Both statements are safe to run on every
-- start and never overwrite user state:
--
--   * the profile is inserted only when its row is absent;
--   * the ten default tickers are inserted only when this user's watchlist is empty, so tickers
--     the user removed are not resurrected by a restart.
--
-- The seed runs as one statement per concern; ids are uuid4-shaped values built with randomblob,
-- timestamps match the application format (ISO-8601 UTC, second precision, trailing "Z").

INSERT OR IGNORE INTO users_profile (id, cash_balance, created_at)
VALUES ('default', 10000.0, strftime('%Y-%m-%dT%H:%M:%SZ', 'now'));

WITH seed(ticker) AS (
    VALUES ('AAPL'), ('GOOGL'), ('MSFT'), ('AMZN'), ('TSLA'),
           ('NVDA'), ('META'), ('JPM'), ('V'), ('NFLX')
)
INSERT INTO watchlist (id, user_id, ticker, added_at)
SELECT lower(
           hex(randomblob(4)) || '-' ||
           hex(randomblob(2)) || '-4' ||
           substr(hex(randomblob(2)), 2) || '-' ||
           substr('89ab', 1 + abs(random() % 4), 1) ||
           substr(hex(randomblob(2)), 2) || '-' ||
           hex(randomblob(6))
       ),
       'default',
       seed.ticker,
       strftime('%Y-%m-%dT%H:%M:%SZ', 'now')
FROM seed
WHERE NOT EXISTS (SELECT 1 FROM watchlist WHERE user_id = 'default');
