from sqlalchemy import update
from sqlalchemy.orm import Session

from app.escrow_chain import ACCEPTED, DISPUTED, FUNDED, REFUNDED, RELEASED, RESOLVED, REVISION, SUBMITTED, Event
from app.marketplace import latest_agreements, plan_released, profile_user_id
from app.models import EscrowAgreement, Job, Project, WorkSubmission
from app.notifications import notify

CLOSED = ("cancelled", "resolved")
NOTICES = {
    FUNDED: {"freelancer": ("ผู้จ้างฝากเงินแล้ว", "เปิดหน้าข้อตกลงแล้วกดรับงานบน Sepolia เพื่อเริ่มงาน")},
    ACCEPTED: {"client": ("ฟรีแลนซ์รับงานแล้ว", "งานเริ่มแล้ว รอการส่งงานตามกำหนด")},
    SUBMITTED: {"client": ("ฟรีแลนซ์ยืนยันส่งงานบน Sepolia", "ตรวจรับ ขอแก้ หรือเปิดข้อพิพาทก่อนหมดช่วงตรวจ")},
    REVISION: {"freelancer": ("ผู้จ้างยืนยันขอแก้งานบน Sepolia", "ตรวจกำหนดส่งใหม่ในหน้าข้อตกลง")},
    DISPUTED: {"client": ("เปิดข้อพิพาทแล้ว", "เงินถูกล็อกจนกว่าจะมีคำตัดสิน"),
               "freelancer": ("เปิดข้อพิพาทแล้ว", "เงินถูกล็อกจนกว่าจะมีคำตัดสิน")},
    RELEASED: {"client": ("จ่ายค่าจ้างสำเร็จ", "ยืนยันบน Sepolia แล้ว"),
               "freelancer": ("ได้รับค่าจ้างแล้ว", "ยืนยันบน Sepolia แล้ว")},
    REFUNDED: {"client": ("คืนเงินแล้ว", "เงินฝากและค่าธรรมเนียมคืนเข้า Wallet ผู้จ้าง"),
               "freelancer": ("คืนเงินให้ผู้จ้างแล้ว", "ข้อตกลงรอบนี้สิ้นสุดแล้ว")},
    RESOLVED: {"client": ("ข้อพิพาทสิ้นสุดแล้ว", "ดูผลการแบ่งเงินในหน้าข้อตกลง"),
               "freelancer": ("ข้อพิพาทสิ้นสุดแล้ว", "ดูผลการแบ่งเงินในหน้าข้อตกลง")},
}
WITHDRAWAL = ("มียอดให้ถอนจากสัญญา", "โอนเข้า Wallet ไม่สำเร็จ กดถอนได้ในหน้ากระเป๋าเงิน")


def send_notice(db: Session, project: Project, agreement: EscrowAgreement, role: str, notice: tuple[str, str]) -> None:
    title, hint = notice
    profile_id = project.client_id if role == "client" else project.freelancer_id
    notify(db, profile_user_id(db, profile_id), "payment", title,
           f"{project.title} · งวด {agreement.milestone_number} · {hint}", f"/{role}/projects/{project.id}/escrow")


def close_job(db: Session, project: Project) -> None:
    db.execute(update(Job).where(Job.id == project.job_id, Job.status == "in_progress").values(status="closed"))


def apply_escrow_event(db: Session, agreement: EscrowAgreement, event: Event, deferred_roles: set[str]) -> None:
    """Move the project along with an event the contract has settled. The caller holds the agreement row."""
    project = db.get(Project, agreement.project_id, with_for_update=True, populate_existing=True)
    if event == DISPUTED and project.status not in CLOSED:
        project.status = "disputed"
    elif event == RELEASED:
        # Releasing, or claiming after the review period, accepts whatever work is still waiting.
        db.execute(update(WorkSubmission).where(
            WorkSubmission.agreement_id == agreement.id, WorkSubmission.status == "pending",
        ).values(status="approved"))
        if plan_released(latest_agreements(db, [project.id]).get(project.id, {})):
            project.status = "completed"
            close_job(db, project)
        elif project.status not in CLOSED:
            project.status = "active"
    elif event == REFUNDED:
        if project.status == "disputed":
            project.status = "resolved"
            close_job(db, project)
        elif project.status not in CLOSED:
            project.status = "active"  # The client can fund another attempt of the same milestone.
    elif event == RESOLVED:
        project.status = "resolved"
        close_job(db, project)
    for role, notice in NOTICES.get(event, {}).items():
        send_notice(db, project, agreement, role, notice)
    for role in sorted(deferred_roles):
        send_notice(db, project, agreement, role, WITHDRAWAL)
