import sqlite3

## Custom sql generation functions
def sql_create_table(db_path, table_name, columns_dict):
    """Create a table from a dict of column definitions."""
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    
    columns_sql = ",\n    ".join(f"{col} {col_type}" for col, col_type in columns_dict.items())
    sql = f"CREATE TABLE IF NOT EXISTS {table_name} (\n    {columns_sql}\n);" 
    cur.execute(sql)
    
    conn.commit()
    conn.close()

def sql_create_table_cmd(table_name, columns_dict):
    """Create a table from a dict of column definitions."""
    columns_sql = ",\n    ".join(f"{col} {col_type}" for col, col_type in columns_dict.items())
    command = f"CREATE TABLE IF NOT EXISTS {table_name} (\n    {columns_sql}\n);" 
    return command

def sql_upsert(table_name, columns, conflict_key): # TODO: Rename with "_cmd" suffix for consistency (and clarity)
    '''Create upset command dynamically.'''
    col_names = [
        c for c in columns.keys()
        if c != "created_on" and c != "updated_on"
    ] # Exclude created_on to enforce default (e.g. 'now')
    insert_cols = ", ".join(col_names)
    placeholders = ", ".join("?" for _ in col_names)
    update_cols = ", ".join(
    f"{c}=COALESCE(excluded.{c}, {c})" # Do not update if NULL is passed to column
    for c in col_names
    if c not in {conflict_key, "updated_on"}
    )
    command = f"""
        INSERT INTO {table_name} ({insert_cols})
        VALUES ({placeholders})
        ON CONFLICT({conflict_key}) DO UPDATE SET
            {update_cols},
            updated_on = DATETIME('now') 
        """ # Updated_on is refreshed here
    return command

def ensure_columns(cur, table_name, columns):
    '''Checking existing tables and ensure/adding columns, allows for dynamic input.'''
    cur.execute(f"PRAGMA table_info({table_name})")
    existing = {row[1] for row in cur.fetchall()}
    # Iterate
    for name, ctype in columns.items():
        if name not in existing:
            cur.execute(f"ALTER TABLE {table_name} ADD COLUMN {name} {ctype}")