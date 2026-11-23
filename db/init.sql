-- Dados exclusivamente didaticos. Nao representam vendas ou estoque de uma empresa.
CREATE TABLE IF NOT EXISTS orders (
    order_id TEXT PRIMARY KEY,
    sku TEXT NOT NULL,
    quantity INTEGER NOT NULL CHECK(quantity > 0),
    simulate_decline BOOLEAN NOT NULL DEFAULT FALSE,
    status TEXT NOT NULL CHECK(status IN ('PENDING','CONFIRMED','REJECTED_STOCK','REJECTED_PAYMENT','MANUAL_REVIEW'))
);
CREATE TABLE IF NOT EXISTS inventory (
    sku TEXT PRIMARY KEY,
    quantity INTEGER NOT NULL CHECK(quantity >= 0)
);
CREATE TABLE IF NOT EXISTS reservations (
    order_id TEXT PRIMARY KEY,
    sku TEXT NOT NULL REFERENCES inventory(sku),
    quantity INTEGER NOT NULL CHECK(quantity > 0)
);
CREATE TABLE IF NOT EXISTS payments (
    order_id TEXT PRIMARY KEY,
    status TEXT NOT NULL CHECK(status IN ('APPROVED','DECLINED'))
);
INSERT INTO inventory(sku,quantity) VALUES ('CAMISETA',100) ON CONFLICT DO NOTHING;
