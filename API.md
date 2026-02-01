# Platform API

## Structure

```
app/
├── core/                    # Shared utilities
│   ├── config.py
│   ├── database.py
│   └── middleware.py
│
├── auth/                    # Authentication
│   ├── models.py
│   ├── services.py
│   └── views.py
│
├── lead_gen/                # Lead Gen Product
│   ├── jobs/                # Jobs API
│   │   ├── model.py
│   │   ├── pipeline.py
│   │   └── routes.py
│   ├── leads/               # Leads API
│   │   ├── model.py
│   │   ├── pipeline.py
│   │   └── routes.py
│   └── credits/             # Credits API
│       ├── model.py
│       ├── pipeline.py
│       └── routes.py
│
├── admin/                   # Admin
│   └── views.py
│
└── payments/                # (placeholder)
```

---

## API Endpoints

### Auth `/api/auth`
| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/register` | Register |
| POST | `/login` | Login |
| GET | `/me` | Current user |

### Lead Gen `/api/lead_gen`

#### Jobs `/api/lead_gen/jobs`
| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/` | Create job |
| GET | `/` | List jobs |
| GET | `/:id` | Get job |
| DELETE | `/:id` | Cancel job |

#### Leads `/api/lead_gen/leads`
| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/job/:id` | Get leads |
| GET | `/job/:id/download` | CSV download |

#### Credits `/api/lead_gen/credits`
| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/` | Balance |
| GET | `/history` | History |

### Admin `/api/admin`
| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/users` | List users |
| POST | `/users/:id/credits` | Add credits |
| GET | `/stats` | Platform stats |
