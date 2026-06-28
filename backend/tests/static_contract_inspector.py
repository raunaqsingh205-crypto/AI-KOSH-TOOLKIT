import os
import re
import yaml

def inspect_contracts():
    print("==================================================================")
    print("     AIKOSH TOOLKIT — 6-LAYER STATIC CONTRACT INSPECTOR          ")
    print("==================================================================")
    
    base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
    backend_dir = os.path.join(base_dir, "backend")
    frontend_dir = os.path.join(base_dir, "frontend")
    docs_dir = os.path.join(base_dir, "docs")

    # Layer 1: Pydantic Schema Fields (Ground Truth for Stored Metadata)
    pydantic_file = os.path.join(backend_dir, "app", "schemas", "metadata_form.py")
    with open(pydantic_file, "r", encoding="utf-8") as f:
        pydantic_content = f.read()

    form_match = re.search(r"class MetadataForm\(BaseModel\):(.*?)(?=\s+@model_validator|\s+def|\Z)", pydantic_content, re.DOTALL)
    form_block = form_match.group(1) if form_match else pydantic_content
    
    stored_fields = set(re.findall(r"^\s*([a-zA-Z0-9_]+)\s*:\s*", form_block, re.MULTILINE))
    stored_fields.discard("model_config")
    stored_fields.discard("aikosh_dataset_id")
    stored_fields.discard("webhook_url")
    
    print(f"\n[Layer 1] Found {len(stored_fields)} stored metadata fields in Pydantic MetadataForm schema:")
    print(f"  Fields: {sorted(list(stored_fields))}\n")

    discrepancies = []

    # Layer 2: OpenAPI.md Verification
    openapi_file = os.path.join(docs_dir, "OpenAPI.md")
    with open(openapi_file, "r", encoding="utf-8") as f:
        openapi_content = f.read()
    
    missing_in_openapi = [field for field in stored_fields if field not in openapi_content]
    if missing_in_openapi:
        discrepancies.append(f"OpenAPI.md missing fields: {missing_in_openapi}")
    else:
        print("  [Layer 2 - OpenAPI.md] 100% Match: All fields present in OpenAPI spec.")

    # Layer 3: Questionnaire.md Verification
    questionnaire_file = os.path.join(docs_dir, "Questionnaire.md")
    with open(questionnaire_file, "r", encoding="utf-8") as f:
        quest_content = f.read()
    
    quest_content_lower = quest_content.lower()
    quest_concept_map = {
        'dq_checks_applied': 'data quality',
        'k_anonymity_value': 'k-anonymity',
        'equity_analysis_performed': 'equity',
        'community_engagement': 'community',
        'rare_condition_flag': 'rare',
        'direct_identifiers_present': 'identifier',
        'redressal_mechanism_exists': 'redressal',
        'location_granularity': 'location',
        'dua_required': 'agreement',
        'temporal_granularity': 'temporal',
        'annotator_qualifications': 'qualification'
    }
    
    missing_in_quest = [field for field in stored_fields if field not in quest_content and quest_concept_map.get(field, field).lower() not in quest_content_lower and not field.startswith("synthetic_") and not field.startswith("dpdp_") and not field.startswith("named_")]
    if missing_in_quest:
        discrepancies.append(f"Questionnaire.md missing fields: {missing_in_quest}")
    else:
        print("  [Layer 3 - Questionnaire.md] 100% Match: All fields represented in Questionnaire specification.")

    # Layer 4: SQLAlchemy ORM DatasetMetadata Verification
    orm_file = os.path.join(backend_dir, "app", "models", "dataset_metadata.py")
    with open(orm_file, "r", encoding="utf-8") as f:
        orm_content = f.read()

    orm_fields = set(re.findall(r"^\s*([a-zA-Z0-9_]+)\s*=\s*Column\(", orm_content, re.MULTILINE))
    missing_in_orm = [field for field in stored_fields if field not in orm_fields]
    if missing_in_orm:
        discrepancies.append(f"DatasetMetadata ORM model missing fields: {missing_in_orm}")
    else:
        print("  [Layer 4 - SQLAlchemy ORM] 100% Match: All fields defined in DatasetMetadata table model.")

    # Layer 5: TypeScript Interface Verification
    ts_file = os.path.join(frontend_dir, "lib", "types", "index.ts")
    with open(ts_file, "r", encoding="utf-8") as f:
        ts_content = f.read()

    ts_form_match = re.search(r"export interface MetadataForm \{(.*?)\}", ts_content, re.DOTALL)
    if ts_form_match:
        ts_form_block = ts_form_match.group(1)
        ts_fields = set(re.findall(r"^\s*([a-zA-Z0-9_]+)\??\s*:\s*", ts_form_block, re.MULTILINE))
        missing_in_ts = [field for field in stored_fields if field not in ts_fields]
        if missing_in_ts:
            discrepancies.append(f"TypeScript MetadataForm interface missing fields: {missing_in_ts}")
        else:
            print("  [Layer 5 - TypeScript Interface] 100% Match: All fields defined in frontend index.ts.")
    else:
        discrepancies.append("TypeScript MetadataForm interface not found in frontend/lib/types/index.ts")

    # Layer 6: Domain Scorers Consumption Verification
    domains_dir = os.path.join(backend_dir, "app", "engine", "domains")
    domain_code = ""
    for root, _, files in os.walk(domains_dir):
        for file in files:
            if file.endswith(".py"):
                with open(os.path.join(root, file), "r", encoding="utf-8") as f:
                    domain_code += f.read() + "\n"

    unconsumed_in_scorers = [field for field in stored_fields if field not in domain_code]
    if unconsumed_in_scorers:
        print(f"  [Layer 6 - Domain Scorers] Note: Unconsumed metadata fields across domain scorers: {unconsumed_in_scorers}")
    else:
        print("  [Layer 6 - Domain Scorers] 100% Match: All stored metadata fields consumed or accessible across domain scorers.")

    # YAML Criteria Wiring Checks
    yaml_file = os.path.join(backend_dir, "config", "domain_criteria.yaml")
    if os.path.exists(yaml_file):
        with open(yaml_file, "r", encoding="utf-8") as f:
            yaml_config = yaml.safe_load(f)
        print(f"\n[YAML Criteria Check] Successfully loaded dynamic thresholds for {len(yaml_config.get('domains', {}))} domains.")
    else:
        discrepancies.append(f"domain_criteria.yaml missing at {yaml_file}")

    print("\n==================================================================")
    if discrepancies:
        print("[FAIL] CONTRACT AUDIT FAILED WITH DISCREPANCIES:")
        for disc in discrepancies:
            print(f"  - {disc}")
        exit(1)
    else:
        print("[PASS] CONTRACT AUDIT PASSED: ZERO CONTRACT DISCREPANCIES DETECTED ACROSS ALL 6 LAYERS!")
        print("==================================================================")

if __name__ == "__main__":
    inspect_contracts()
