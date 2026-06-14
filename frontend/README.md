# DataLeadHub Frontend

Next.js + TypeScript cabinet for the multi-user parsers platform.

## Local run

```bash
cd frontend
npm install
NEXT_PUBLIC_API_URL=http://localhost:8000/api/v1 npm run dev
```

Open:

```text
http://localhost:3000
```

## Pages

- `/` - login and registration
- `/jobs` - main parser launcher, queue, and job history
- `/results` - database records and CSV/XLSX/JSON export
- `/billing` - plans, invoices, and payment flow placeholder
- `/notifications` - in-app notifications
- `/admin` - users, invoices, and audit log for admins

The first registered user becomes admin on the backend side.
