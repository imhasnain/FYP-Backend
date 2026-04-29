from database import get_connection
conn = get_connection()
cur = conn.cursor()

print("=== CHECK CONSTRAINTS ===")
cur.execute("""
    SELECT cc.name AS constraint_name,
           t.name  AS table_name,
           cc.definition
    FROM sys.check_constraints cc
    JOIN sys.tables t ON cc.parent_object_id = t.object_id
    WHERE t.name IN ('SensorData', 'MH_Results')
    ORDER BY t.name, cc.name
""")
for r in cur.fetchall():
    print(f"\nTable : {r.table_name}")
    print(f"Constraint: {r.constraint_name}")
    print(f"Definition: {r.definition}")

conn.close()
