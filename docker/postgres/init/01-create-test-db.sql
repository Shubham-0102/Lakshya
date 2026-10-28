-- A separate database for tests, so they never touch real data.
-- Runs once, when the Postgres volume is first created.
CREATE DATABASE lakshya_test;
