# Todo API with Azure Blob CSV Export

A simple Todo REST API built with FastAPI, SQLAlchemy, and Azure Blob Storage for exporting todos as CSV files with secure, time-limited access links.

---

## Features

- Create, read, update, delete (CRUD) Todos
- Secure API key authentication
- Export all todos as a CSV file uploaded to Azure Blob Storage
- Generates a secure, time-limited SAS URL to download the CSV

---

## Prerequisites

- Python 3.9+
- An Azure Storage Account with Blob Storage enabled
- Azure Storage Connection String
- API key for authorization

---

## Setup Instructions

1. **Clone the repository**

```bash
git clone https://github.com/EmanRehman/task12
cd yourrepo
