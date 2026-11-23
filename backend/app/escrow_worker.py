import json
import logging
from time import sleep

import httpx
from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db import get_engine
from app.escrow import get_transaction, reconcile
from app.escrow_chain import EVENTS, EscrowChain
from app.models import EscrowAgreement, EscrowTransaction

logger = logging.getLogger(__name__)
BLOCKS_PER_SCAN = 500


def scan_agreement(db: Session, chain: EscrowChain, agreement: EscrowAgreement, finalized: dict) -> None:
    finalized_number = int(finalized["number"], 16)
    start = agreement.next_scan_block
    end = min(start + BLOCKS_PER_SCAN - 1, finalized_number)
    if start <= end:
        logs = chain.call("eth_getLogs", {
            "address": agreement.contract_address,
            "fromBlock": hex(start), "toBlock": hex(end),
            "topics": [list(EVENTS), agreement.expected_escrow_id],
        })
        logs.sort(key=lambda log: (int(log["blockNumber"], 16), int(log["logIndex"], 16)))
        for tx_hash in dict.fromkeys(log["transactionHash"].lower() for log in logs):
            tx = get_transaction(db, agreement, tx_hash)
            reconcile(db, chain, agreement, tx, finalized)
            if tx.status == "pending":
                return  # Retry this range if the receipt is temporarily unavailable.
        if (end == finalized_number and agreement.status == "prepared"
                and int(finalized["timestamp"], 16) >= json.loads(agreement.terms_json)["deadline"]
                and not chain.is_occupied(agreement.contract_address, agreement.expected_escrow_id, hex(end))):
            agreement.status = "expired"
        agreement.next_scan_block = end + 1
    pending = db.scalars(select(EscrowTransaction).where(
        EscrowTransaction.agreement_id == agreement.id, EscrowTransaction.status == "pending",
    ).limit(20)).all()
    for tx in pending:
        reconcile(db, chain, agreement, tx, finalized)


def sync_once() -> None:
    settings = get_settings()
    with httpx.Client(timeout=5) as http, Session(get_engine()) as db:
        ids = db.scalars(select(EscrowAgreement.id).where(
            EscrowAgreement.chain_id == settings.escrow_chain_id,
            EscrowAgreement.status.in_(("prepared", "funded")),
        ).order_by(EscrowAgreement.next_scan_block)).all()
        db.rollback()
        if not ids:
            return
        chain = EscrowChain(http, settings.escrow_chain_id)
        finalized = chain.block()
        for agreement_id in ids:
            try:
                agreement = db.get(EscrowAgreement, agreement_id, with_for_update={"skip_locked": True})
                if agreement is not None and agreement.status in ("prepared", "funded"):
                    before = agreement.status
                    scan_agreement(db, chain, agreement, finalized)
                    after = agreement.status
                    db.commit()
                    if before != after:
                        logger.info("Escrow agreement %s changed from %s to %s", agreement_id, before, after)
                    continue
                db.commit()
            except (HTTPException, KeyError, TypeError, ValueError):
                db.rollback()
                logger.warning("Could not sync escrow agreement %s. Its block range will be retried.", agreement_id)


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    logger.info("Escrow worker started")
    while True:
        try:
            sync_once()
        except HTTPException as exc:
            logger.warning("Escrow RPC request failed with status %s. Retrying.", exc.status_code)
        except SQLAlchemyError:
            logger.warning("Escrow database request failed. Retrying.")
        sleep(15)


if __name__ == "__main__":
    main()
