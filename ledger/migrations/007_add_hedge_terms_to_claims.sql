-- Forward-only migration 007: hedge terms found in each claim's source sentence (S5, Check C)
ALTER TABLE claims ADD COLUMN hedge_terms_json TEXT;
