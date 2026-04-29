from database import get_connection
conn = get_connection()
cur = conn.cursor()

tables = ["FacialEmotions", "MH_Results", "Enrollments", "Students", "Teachers"]
for t in tables:
    print(f"\n=== {t} ===")
    try:
        cur.execute(
            "SELECT COLUMN_NAME, DATA_TYPE, IS_NULLABLE "
            "FROM INFORMATION_SCHEMA.COLUMNS "
            "WHERE TABLE_NAME = ? ORDER BY ORDINAL_POSITION",
            (t,)
        )
        rows = cur.fetchall()
        if rows:
            for r in rows:
                print(f"  {r.COLUMN_NAME:35s} {r.DATA_TYPE:15s} nullable={r.IS_NULLABLE}")
        else:
            print("  [TABLE DOES NOT EXIST]")
    except Exception as e:
        print(f"  ERROR: {e}")

conn.close()
