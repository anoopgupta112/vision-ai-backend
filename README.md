# Lead Extractor Landing Page

A professional, modern landing page for the Lead Extractor application built with Flask backend and responsive frontend design.

## Features

- **Modern Design**: Gradient-based color scheme with smooth animations
- **Fully Responsive**: Mobile-first design that works on all devices
- **Flask Backend**: Clean, modular Flask application
- **SEO Optimized**: Proper meta tags and semantic HTML
- **Premium UI**: Glassmorphism effects, hover animations, and micro-interactions
- **Custom Error Pages**: Beautiful 404 and 500 error pages

## Tech Stack

- **Backend**: Flask 3.0
- **Frontend**: HTML5, CSS3, Vanilla JavaScript
- **Fonts**: Google Fonts (Inter, Poppins)
- **Deployment**: Gunicorn ready for production

## Setup Instructions

### Prerequisites

- Python 3.9+
- pip

### Installation

1. **Clone and Navigate**
   ```bash
   cd /Users/anoopchandra/repositories/main_dashboard
   ```

2. **Create Virtual Environment**
   ```bash
   python3 -m venv .venv
   source .venv/bin/activate
   ```

3. **Install Dependencies**
   ```bash
   pip install -r requirements.txt
   ```

4. **Configure Environment**
   ```bash
   cp .env.example .env
   ```
   
   Edit `.env` and update:
   - `SECRET_KEY`: Generate a secure random key
   - `DASHBOARD_URL`: URL of your dashboard (e.g., `https://app.leadextractor.com`)

5. **Run Development Server**
   ```bash
   python app.py
   ```
   
   The application will be available at `http://localhost:8000`

### Production Deployment

For production, use Gunicorn:

```bash
gunicorn --bind 0.0.0.0:8000 --workers 4 app:create_app()
```

Or with environment variables:

```bash
export FLASK_ENV=production
gunicorn --bind 0.0.0.0:8000 --workers 4 app:create_app()
```

### Docker Deployment

**Build and Run**

```bash
# Build the Docker image
docker-compose build

# Start the container
docker-compose up -d

# View logs
docker-compose logs -f

# Stop the container
docker-compose down
```

**Production with Custom Environment**

```bash
# Set environment variables in .env file
export FLASK_ENV=production
export SECRET_KEY=your-production-secret-key
export DASHBOARD_URL=https://app.yourdomain.com

# Start with environment variables
docker-compose up -d
```

**Health Check**

The container includes health checks on the `/health` endpoint:
```bash
# Check container health
docker-compose ps

# Manual health check
curl http://localhost:8000/health
```

## Project Structure

```
main_dashboard/
├── app.py                 # Main Flask application
├── config.py             # Configuration management
├── requirements.txt      # Python dependencies
├── .env.example         # Environment variables template
├── .gitignore          # Git ignore rules
├── static/
│   └── css/
│       └── style.css   # All styling
└── templates/
    ├── base.html       # Base template
    ├── index.html      # Landing page
    ├── 404.html        # 404 error page
    └── 500.html        # 500 error page
```

## Configuration

### Environment Variables

- `FLASK_ENV`: Set to `development` or `production`
- `SECRET_KEY`: Flask secret key for sessions
- `DASHBOARD_URL`: URL of the dashboard application

### Customization

**Update Dashboard URL**: Edit `.env` file and change `DASHBOARD_URL`

**Change Colors**: Edit `static/css/style.css` and modify CSS variables in `:root`

**Update Content**: Edit `templates/index.html` to change text, features, pricing, etc.

## Features Overview

### Landing Page Sections

1. **Navigation Bar**
   - Fixed header with smooth scroll
   - Mobile-responsive hamburger menu
   - Quick access to dashboard

2. **Hero Section**
   - Eye-catching headline with gradient text
   - Call-to-action buttons
   - Key statistics display

3. **Features Section**
   - 6 feature cards with icons
   - Hover animations
   - Grid layout (responsive)

4. **How It Works**
   - 4-step process visualization
   - Numbered step cards
   - Clear workflow explanation

5. **Pricing Section**
   - 3 tier pricing cards
   - Featured plan highlighting
   - Clear feature lists

6. **Call-to-Action**
   - Final conversion section
   - Dashboard access button

7. **Footer**
   - Product, support, and legal links
   - Multi-column layout
   - Copyright information

### Design Highlights

- **Color Scheme**: Purple/blue gradients with vibrant accents
- **Typography**: Inter (body), Poppins (headings)
- **Animations**: Fade-in effects, smooth transitions, hover states
- **Responsive**: Breakpoints at 768px (mobile) and 1024px (tablet)

## API Endpoints

- `GET /` - Landing page
- `GET /health` - Health check endpoint (returns JSON)

## Error Handling

The application includes custom error handlers for:
- 404 Not Found
- 500 Internal Server Error
- General exceptions (logged and displayed as 500)

## Browser Compatibility

- Chrome (latest)
- Firefox (latest)
- Safari (latest)
- Edge (latest)
- Mobile browsers (iOS Safari, Chrome Mobile)

## Performance

- Lightweight CSS (no frameworks)
- Optimized fonts loading
- Minimal JavaScript
- Fast page load times

## License

Proprietary - All rights reserved

## Support

For issues or questions, contact the development team or refer to the Lead Extractor dashboard documentation.
