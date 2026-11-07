-- Publication is a derived gate; retained revisions and orders are never rewritten.
-- All completed risk levels may publish: risk is advisory, with High acknowledgement at checkout.
CREATE FUNCTION listing_publication_allowed(p_product bigint) RETURNS boolean
LANGUAGE sql VOLATILE AS $$
    SELECT EXISTS(SELECT 1 FROM current_listing_risk
                  WHERE product_id=p_product AND assessment_state='ready')
$$;
CREATE FUNCTION guard_scanned_purchase() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    IF NOT listing_publication_allowed(NEW.product_id) THEN
        RAISE EXCEPTION 'A current successful assessment is required before purchase' USING ERRCODE='23514';
    END IF;
    RETURN NEW;
END $$;
CREATE TRIGGER order_scan_publication_guard BEFORE INSERT ON transactions
FOR EACH ROW EXECUTE FUNCTION guard_scanned_purchase();
-- Trigger is definer-owned for least-privilege web connections, as in privilege setup.
ALTER FUNCTION guard_scanned_purchase() SECURITY DEFINER SET search_path=public,pg_temp;
REVOKE ALL ON FUNCTION guard_scanned_purchase() FROM PUBLIC;

REVOKE ALL ON FUNCTION listing_publication_allowed(bigint) FROM PUBLIC;
DO $$ BEGIN
    IF EXISTS(SELECT 1 FROM pg_roles WHERE rolname='secondhand_web') THEN
        GRANT EXECUTE ON FUNCTION listing_publication_allowed(bigint) TO secondhand_web;
    END IF;
END $$;
