import logging
from fastapi import APIRouter, HTTPException, status
from database import get_connection

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/advisor", tags=["Advisor"])

@router.get("/{advisor_id}/students")
def get_advisor_students(advisor_id: int):
    """Get all medium stress students assigned to this advisor via notifications."""
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT n.notification_id, n.student_id, u.name as student_name, 
                   n.session_id, n.message, n.created_at, n.is_read, m.risk_class
            FROM AdvisorNotifications n
            JOIN Users u ON n.student_id = u.user_id
            JOIN MH_Results m ON n.session_id = m.session_id
            WHERE n.advisor_id = ?
            ORDER BY n.created_at DESC
        """, (advisor_id,))
        rows = cursor.fetchall()
        return {"students": [
            {
                "notification_id": r[0],
                "student_id": r[1],
                "student_name": r[2],
                "session_id": r[3],
                "message": r[4],
                "created_at": r[5].isoformat() if r[5] else None,
                "is_read": r[6],
                "risk_class": r[7]
            } for r in rows
        ]}
    except Exception as exc:
        logger.exception("Error getting advisor students: %s", exc)
        raise HTTPException(status_code=500, detail="Could not fetch students.")
    finally:
        conn.close()

