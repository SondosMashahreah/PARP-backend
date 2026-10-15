-- The committee account is now stored independently in committee_accounts.
-- Run this only after the backend starts successfully and committee_accounts exists.
DROP TABLE IF EXISTS committee_credentials;
