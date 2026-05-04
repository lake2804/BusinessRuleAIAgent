#!/usr/bin/env python3
"""Test full workflow: create domain, ingest files, test query."""

import sys
import os
import requests
import json
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

# API endpoints
RAG_API_URL = "http://localhost:8601"
REVIEW_API_URL = "http://localhost:8602"

def test_rag_api_health():
    """Test if RAG API is running."""
    try:
        response = requests.get(f"{RAG_API_URL}/domains")
        return response.status_code == 200
    except:
        return False

def test_review_api_health():
    """Test if Review API is running."""
    try:
        response = requests.get(f"{REVIEW_API_URL}/uploads")
        return response.status_code == 200
    except:
        return False

def create_test_domain():
    """Create a new test domain."""
    domain_data = {
        "domain_id": "test_workflow_new",
        "name": "Test Workflow Domain",
        "description": "Domain for testing full workflow"
    }
    
    response = requests.post(f"{RAG_API_URL}/domains", json=domain_data)
    if response.status_code == 201:
        print("✅ Domain 'test_workflow_new' created successfully")
        return True
    else:
        print(f"❌ Failed to create domain: {response.text}")
        return False

def ingest_test_files():
    """Ingest test files into the new domain."""
    # Use existing test files from test6 domain
    files_to_ingest = [
        "README_Test_Pack.md",
        "ORR_Policy_Manual_v1_4_ACTIVE.docx",
        "ORR_Regional_Overrides_ACTIVE.md",
        "ORR_Regional_Policy_Overrides_Table.csv",
        "ORR_Sample_Cases_and_Expected_Outcomes.json",
        "ORR_Workflow_and_Decision_Notes.md",
        "ORR_Exception_SLA_and_Escalation_Handbook.pdf",
        "ORR_Field_Mapping_and_Rule_Matrix.xlsx"
    ]
    
    # Get file paths from data/uploads
    upload_dir = ROOT / "data" / "uploads"
    
    success_count = 0
    for filename in files_to_ingest:
        file_path = upload_dir / filename
        if file_path.exists():
            with open(file_path, 'rb') as f:
                files = {'file': f}
                data = {
                    'domain_id': 'test_workflow_new',
                    'ruleset_name': 'Test Ruleset',
                    'version': '1.0.0'
                }
                response = requests.post(f"{RAG_API_URL}/ingest", files=files, data=data)
                if response.status_code in [201, 207]:
                    success_count += 1
                    print(f"✅ Ingested {filename}")
                else:
                    print(f"❌ Failed to ingest {filename}: {response.text}")
        else:
            print(f"⚠️ File not found: {filename}")
    
    print(f"✅ Successfully ingested {success_count}/{len(files_to_ingest)} files")
    return success_count > 0

def test_query():
    """Test the query on the new domain."""
    query_data = {
        "query": "what business rules are contained in this domain?",
        "domainId": "test_workflow_new",
        "uploadIds": []
    }
    
    response = requests.post(f"{REVIEW_API_URL}/run", json=query_data)
    if response.status_code == 200:
        result = response.json()
        answer = result.get("result", {}).get("answer", "")
        evidence_count = result.get("result", {}).get("evidence_count", 0)
        confidence = result.get("result", {}).get("confidence", {})
        
        print(f"✅ Query successful!")
        print(f"📊 Evidence count: {evidence_count}")
        print(f"🎯 Confidence: {confidence}")
        print(f"📝 Answer preview: {answer[:200]}...")
        
        if evidence_count > 0:
            return True
        else:
            print("❌ No evidence found")
            return False
    else:
        print(f"❌ Query failed: {response.text}")
        return False

def main():
    """Run the full workflow test."""
    print("🚀 Starting Full Workflow Test")
    print("=" * 50)
    
    # Test API health
    print("\n1. Testing API Health...")
    if not test_rag_api_health():
        print("❌ RAG API is not running on port 8601")
        return
    if not test_review_api_health():
        print("❌ Review API is not running on port 8602")
        return
    print("✅ Both APIs are running")
    
    # Create domain
    print("\n2. Creating Test Domain...")
    if not create_test_domain():
        return
    
    # Wait a moment
    time.sleep(1)
    
    # Ingest files
    print("\n3. Ingesting Test Files...")
    if not ingest_test_files():
        print("❌ Failed to ingest files")
        return
    
    # Wait for ingestion to complete
    print("\n⏳ Waiting for ingestion to complete...")
    time.sleep(5)
    
    # Test query
    print("\n4. Testing Query...")
    if test_query():
        print("\n🎉 Full workflow test PASSED!")
    else:
        print("\n❌ Full workflow test FAILED!")

if __name__ == "__main__":
    main()
