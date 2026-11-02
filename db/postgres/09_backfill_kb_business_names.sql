UPDATE sqlpilot_kb.schema_documents
SET business_name = split_part(
    COALESCE(NULLIF(metadata ->> 'column_comment', ''), NULLIF(metadata ->> 'comment', ''), object_key),
    '；', 1
)
WHERE COALESCE(business_name, '') = '';
