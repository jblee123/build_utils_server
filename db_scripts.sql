CREATE TABLE IF NOT EXISTS "main"."product" (
    "id" INTEGER PRIMARY KEY AUTOINCREMENT NOT NULL UNIQUE,
    "name" TEXT NOT NULL);

CREATE TABLE IF NOT EXISTS "main"."version" (
    "id" INTEGER PRIMARY KEY AUTOINCREMENT NOT NULL,
    "product_id" INTEGER NOT NULL,
    "version_str" TEXT NOT NULL,
    FOREIGN KEY ("product_id") REFERENCES "product"("id"));

CREATE TABLE IF NOT EXISTS "main"."build" (
    "id" INTEGER PRIMARY KEY AUTOINCREMENT NOT NULL,
    "version_id" INTEGER NOT NULL,
    "build_num" INTEGER NOT NULL,
    "timestamp" DATETIME NOT NULL,
    "commit_id" TEXT NOT NULL,
    FOREIGN KEY ("version_id") REFERENCES "version"("id"));
