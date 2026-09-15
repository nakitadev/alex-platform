# Infrastructure as Code (Terraform)

This directory contains modular Terraform definitions for the Alex platform:

## Modules (`infra/modules/`)
- `sagemaker`: HuggingFace embedding endpoint (all-MiniLM-L6-v2)
- `ingestion`: S3 Vectors storage, Ingest Lambda, and API Gateway
- `researcher`: App Runner container service for autonomous web research
- `database`: Aurora Serverless v2 PostgreSQL with Data API enabled
- `agents`: 5 Lambda agents (Planner, Tagger, Reporter, Charter, Retirement) + SQS queue
- `frontend`: Next.js S3 static hosting, CloudFront CDN, and FastAPI Lambda Gateway
- `enterprise`: CloudWatch monitoring dashboards, alarms, and security policies

## Deploying
Each module can be applied independently using its local state:
```bash
cd infra/modules/agents
cp terraform.tfvars.example terraform.tfvars
terraform init
terraform apply
```
Or run the unified deployment script:
```bash
uv run scripts/deploy/deploy_agents.py
```
