import json
import os
import uvicorn
from datetime import date, datetime, timedelta
from pathlib import Path
from dotenv import load_dotenv

from fastapi import FastAPI, File, Request, Query, HTTPException, Depends
from fastapi.responses import RedirectResponse, HTMLResponse, FileResponse, Response
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware
from fastapi.staticfiles import StaticFiles

from sqlalchemy import create_engine, Column, Integer, String, Date, desc, text, func
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, Session
from config import DOC_URLS

# Load environment variables from .env file
load_dotenv()

# Database setup
DATABASE_URL = os.environ.get('DATABASE_URL')
if not DATABASE_URL:
    raise ValueError("DATABASE_URL environment variable is not set")

if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

# Add error handling for database connection
try:
    engine = create_engine(DATABASE_URL)
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    Base = declarative_base()
except Exception as e:
    raise RuntimeError(f"Failed to connect to database: {str(e)}")

class Download(Base):
    __tablename__ = "downloads"
    id = Column(Integer, primary_key=True)         # 4 bytes
    package = Column(String)                       # variable
    date = Column(Date)                           # 4 bytes
    count = Column(Integer)                       # 4 bytes
    platform = Column(String)                     # variable

# Create tables
Base.metadata.create_all(bind=engine)

# Dependency
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

app = FastAPI()
# Add SessionMiddleware with a secret key
app.add_middleware(
    SessionMiddleware,
    secret_key="your-secret-key-here"  # Replace with a secure secret key
)

# Mount static files directory
app.mount("/css", StaticFiles(directory="templates/css"), name="css")
app.mount("/images", StaticFiles(directory="templates/images"), name="images")

templates = Jinja2Templates(directory="templates")

# ============================================================================
# BADGE GENERATION FUNCTIONS
# ============================================================================

def format_number(num: int) -> str:
    """Format large numbers with k/M suffix"""
    if num >= 1_000_000:
        return f"{num / 1_000_000:.1f}M"
    if num >= 1_000:
        return f"{num / 1_000:.1f}k"
    return str(num)

def generate_badge_svg(label: str, value: str, color: str = 'blue') -> str:
    """Generate an SVG badge similar to shields.io/CRAN style"""
    
    # Color schemes matching CRAN badges
    colors = {
        'blue': '#007ec6',
        'green': '#4c1',
        'brightgreen': '#44cc11',
        'orange': '#fe7d37',
        'red': '#e05d44',
        'lightgrey': '#9f9f9f',
        'yellowgreen': '#a4a61d',
        'yellow': '#dfb317'
    }
    
    right_color = colors.get(color, colors['blue'])
    left_color = '#555'
    
    # Calculate text widths (approximate, matches shields.io closely)
    char_width = 6.5
    padding = 10
    left_width = int(len(label) * char_width + padding)
    right_width = int(len(str(value)) * char_width + padding)
    total_width = left_width + right_width
    
    svg = f'''<svg xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink" width="{total_width}" height="20" role="img" aria-label="{label}: {value}">
    <title>{label}: {value}</title>
    <linearGradient id="s" x2="0" y2="100%">
        <stop offset="0" stop-color="#bbb" stop-opacity=".1"/>
        <stop offset="1" stop-opacity=".1"/>
    </linearGradient>
    <clipPath id="r">
        <rect width="{total_width}" height="20" rx="3" fill="#fff"/>
    </clipPath>
    <g clip-path="url(#r)">
        <rect width="{left_width}" height="20" fill="{left_color}"/>
        <rect x="{left_width}" width="{right_width}" height="20" fill="{right_color}"/>
        <rect width="{total_width}" height="20" fill="url(#s)"/>
    </g>
    <g fill="#fff" text-anchor="middle" font-family="Verdana,Geneva,DejaVu Sans,sans-serif" text-rendering="geometricPrecision" font-size="110">
        <text aria-hidden="true" x="{left_width * 10 // 2}" y="150" fill="#010101" fill-opacity=".3" transform="scale(.1)" textLength="{(left_width - padding) * 10}">{label}</text>
        <text x="{left_width * 10 // 2}" y="140" transform="scale(.1)" fill="#fff" textLength="{(left_width - padding) * 10}">{label}</text>
        <text aria-hidden="true" x="{(left_width + right_width // 2) * 10}" y="150" fill="#010101" fill-opacity=".3" transform="scale(.1)" textLength="{(right_width - padding) * 10}">{value}</text>
        <text x="{(left_width + right_width // 2) * 10}" y="140" transform="scale(.1)" fill="#fff" textLength="{(right_width - padding) * 10}">{value}</text>
    </g>
</svg>'''
    
    return svg

def get_download_count_from_db(package: str, period: str, db: Session) -> int:
    """Get download count for a package from the database"""
    today = date.today()
    
    if period == "last-day":
        start_date = today - timedelta(days=1)
    elif period == "last-week":
        start_date = today - timedelta(days=7)
    elif period == "last-month":
        start_date = today - timedelta(days=30)
    elif period == "grand-total":
        start_date = None
    else:
        raise HTTPException(status_code=400, detail="Invalid period")
    
    query = db.query(func.sum(Download.count)).filter(
        Download.package == package
    )
    
    if start_date:
        query = query.filter(Download.date >= start_date)
    
    result = query.scalar()
    return result if result else 0

# ============================================================================
# BADGE ENDPOINTS
# ============================================================================

@app.get("/badges/downloads/{period}/{package}.svg")
async def badge_svg(
    package: str,
    period: str,
    color: str = Query(default="blue", description="Badge color"),
    db: Session = Depends(get_db)
):
    """
    Generate an SVG badge for package downloads
    
    - **package**: Package name
    - **period**: Time period (last-day, last-week, last-month, grand-total)
    - **color**: Badge color (blue, green, brightgreen, orange, red, yellow, yellowgreen, lightgrey, auto)
    
    Example: /badges/downloads/last-month/ggplot2.svg?color=brightgreen
    """
    
    # Map period to label
    period_labels = {
        "last-day": "downloads/day",
        "last-week": "downloads/week",
        "last-month": "downloads/month",
        "grand-total": "total downloads"
    }
    
    label = period_labels.get(period, "downloads")
    
    try:
        count = get_download_count_from_db(package, period, db)
        value = format_number(count)
        
        # Auto color based on download count
        if color == "auto":
            if count > 100_000:
                color = "brightgreen"
            elif count > 10_000:
                color = "green"
            elif count > 1_000:
                color = "yellowgreen"
            elif count > 100:
                color = "blue"
            else:
                color = "lightgrey"
        
        svg_content = generate_badge_svg(label, value, color)
        
        return Response(
            content=svg_content,
            media_type="image/svg+xml",
            headers={
                "Cache-Control": "max-age=3600",  # Cache for 1 hour
                "Content-Disposition": f"inline; filename={package}-{period}.svg"
            }
        )
    except Exception as e:
        # Return error badge
        svg_content = generate_badge_svg(label, "error", "lightgrey")
        return Response(content=svg_content, media_type="image/svg+xml")

@app.get("/downloads/total/{period}/{package}")
async def get_total_downloads(
    package: str, 
    period: str,
    db: Session = Depends(get_db)
):
    """
    Get total download count as JSON (CRAN logs API compatible)
    
    Returns download statistics for the specified package and period
    """
    try:
        count = get_download_count_from_db(package, period, db)
        
        # Calculate date range based on period
        end_date = date.today()
        if period == "last-day":
            start_date = end_date - timedelta(days=1)
        elif period == "last-week":
            start_date = end_date - timedelta(days=7)
        elif period == "last-month":
            start_date = end_date - timedelta(days=30)
        else:
            start_date = None
        
        return [{
            "start": str(start_date) if start_date else None,
            "end": str(end_date),
            "downloads": count,
            "package": package
        }]
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/downloads/daily/{package}")
async def get_daily_downloads(
    package: str,
    from_date: str = Query(None, description="Start date (YYYY-MM-DD)"),
    to_date: str = Query(None, description="End date (YYYY-MM-DD)"),
    db: Session = Depends(get_db)
):
    """
    Get daily download counts for a package (CRAN logs API compatible)
    
    Returns detailed daily download statistics
    """
    try:
        query = db.query(
            Download.date,
            func.sum(Download.count).label('count')
        ).filter(
            Download.package == package
        )
        
        if from_date:
            query = query.filter(Download.date >= from_date)
        if to_date:
            query = query.filter(Download.date <= to_date)
        
        results = query.group_by(Download.date).order_by(Download.date).all()
        
        return [
            {
                "date": str(row.date),
                "count": row.count,
                "package": package
            }
            for row in results
        ]
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# ============================================================================
# EXISTING ENDPOINTS (unchanged)
# ============================================================================

@app.get("/", response_class=HTMLResponse, include_in_schema=False)
async def get_index(request: Request, db: Session = Depends(get_db)):
    try:
        packages = {}
        r_packages_dir = Path("r-packages")
        
        # Get latest version for each package from r-packages/src/contrib
        src_contrib = r_packages_dir / "src" / "contrib"
        if src_contrib.exists():
            for tar_gz in src_contrib.glob("*.tar.gz"):
                package_name = tar_gz.name.split("_")[0]
                version = tar_gz.name.split("_")[1].replace(".tar.gz", "")
                if package_name not in packages:
                    packages[package_name] = {
                        "package": package_name,
                        "version": version,
                        "platforms": {
                            "source": {
                                "status": "SUCCESS",
                                "build_time": datetime.fromtimestamp(tar_gz.stat().st_mtime).strftime("%Y-%m-%d %H:%M:%S")
                            }
                        }
                    }

        # Check Windows binaries for all R versions
        for r_version in ["4.2", "4.3", "4.4"]:
            win_dir = r_packages_dir / "bin" / "windows" / "contrib" / r_version
            if win_dir.exists():
                for zip_file in win_dir.glob("*.zip"):
                    package_name = zip_file.name.split("_")[0]
                    if package_name in packages:
                        packages[package_name]["platforms"]["windows"] = {
                            "status": "SUCCESS",
                            "build_time": datetime.fromtimestamp(zip_file.stat().st_mtime).strftime("%Y-%m-%d %H:%M:%S"),
                            "r_version": r_version
                        }

        # Check macOS binaries for all R versions
        for r_version in ["4.2", "4.3", "4.4"]:
            mac_dir = r_packages_dir / "bin" / "macosx" / "contrib" / r_version
            if mac_dir.exists():
                for tgz_file in mac_dir.glob("*.tgz"):
                    package_name = tgz_file.name.split("_")[0]
                    if package_name in packages:
                        packages[package_name]["platforms"]["macos"] = {
                            "status": "SUCCESS",
                            "build_time": datetime.fromtimestamp(tgz_file.stat().st_mtime).strftime("%Y-%m-%d %H:%M:%S"),
                            "r_version": r_version
                        }

        # Read build status files to get list of all packages that should exist
        for json_file in r_packages_dir.glob("build_status_*.json"):
            with open(json_file) as f:
                build_info = json.load(f)
                platform = build_info.get("platform", "unknown")
                for pkg_name, pkg_info in build_info.get("packages", {}).items():
                    if pkg_name not in packages:
                        if pkg_name not in packages:
                            packages[pkg_name] = {
                                "package": pkg_name,
                                "version": "",
                                "platforms": {}
                            }
                        packages[pkg_name]["platforms"][platform] = {
                            "status": "FAILED",
                            "build_time": pkg_info.get("build_time", ""),
                            "error_message": "No package file found"
                        }

        return templates.TemplateResponse(
            "index.html", 
            {
                "request": request, 
                "year": datetime.now().year,
                "packages": packages,
                "downloads": db.query(Download).order_by(desc(Download.date)).all()
            }
        )
    except Exception as e:
        print(f"Error in get_index: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/download/{package}")
async def download_package(
    package: str, 
    version: str = Query(..., description="R package version"),
    platform: str = Query(default="source", description="Platform (windows/macos/source)"),
    r_version: str = Query(default="4.3", description="R version (e.g. 4.3)"),
    db: Session = Depends(get_db)
):
    try:
        today = date.today()
        
        print(f"Download request: package={package}, version={version}, platform={platform}")
        
        download = db.query(Download).filter(
            Download.package == package,
            Download.date == today,
            Download.platform == platform
        ).first()
        
        if not download:
            download = Download(
                package=package,
                date=today,
                count=1,
                platform=platform
            )
            db.add(download)
        else:
            db.query(Download).filter(
                Download.id == download.id
            ).update(
                {"count": Download.count + 1},
                synchronize_session=False
            )
        
        db.commit()
        
        base_url = "https://r-packages.techtonique.net"
        if platform == "windows":
            package_url = f"{base_url}/bin/windows/contrib/{r_version}/{package}_{version}.zip"
        elif platform == "macos":
            package_url = f"{base_url}/bin/macosx/contrib/{package}_{version}.tgz"
        else:
            package_url = f"{base_url}/src/contrib/{package}_{version}.tar.gz"
        
        print(f"Redirecting to: {package_url}")
        
        return RedirectResponse(url=package_url)
        
    except Exception as e:
        print(f"Error in download_package: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/download/source/{package}")
async def download_source_package(
    package: str, 
    version: str = Query(..., description="R package version"),
    db: Session = Depends(get_db)
):
    try:
        today = date.today()
        file_path = f"r-packages/src/contrib/{package}_{version}.tar.gz"
        
        if not os.path.exists(file_path):
            raise HTTPException(
                status_code=404,
                detail=f"Package file not found: {file_path}"
            )
            
        download = db.query(Download).filter(
            Download.package == package,
            Download.date == today,
            Download.platform == "source"
        ).first()
        
        if not download:
            download = Download(
                package=package,
                date=today,
                count=1,
                platform="source"
            )
            db.add(download)
        else:
            db.query(Download).filter(
                Download.id == download.id
            ).update(
                {"count": Download.count + 1},
                synchronize_session=False
            )
        
        db.commit()
        
        return FileResponse(
            path=file_path,
            filename=os.path.basename(file_path),
            media_type="application/octet-stream"
        )
        
    except Exception as e:
        print(f"Error in download_source_package: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/stats/{date}/{package}")
async def get_stats(date: str, package: str, db: Session = Depends(get_db)):
    try:
        downloads = db.query(Download).filter(
            Download.package == package,
            Download.date == date
        ).all()
        
        if not downloads:
            return {"package": package, "date": date, "total_count": 0, "by_platform": {}}
            
        total_count = sum(d.count for d in downloads)
        by_platform = {
            d.platform: {
                "count": d.count,
                "date": d.date.isoformat()
            } for d in downloads
        }
            
        return {
            "package": package,
            "date": date,
            "total_count": total_count,
            "by_platform": by_platform
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/stats/today")
async def get_today_stats(db: Session = Depends(get_db)):
    try:
        today = date.today()
        downloads = db.query(Download).filter(Download.date == today).all()
        return [
            {
                "package": d.package,
                "date": d.date.isoformat(),
                "count": d.count,
                "platform": d.platform
            } 
            for d in downloads
        ]
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/src/contrib/PACKAGES")
@app.get("/src/contrib/PACKAGES.gz")
@app.get("/src/contrib/PACKAGES.rds")
@app.get("/bin/windows/contrib/{r_version}/PACKAGES")
@app.get("/bin/windows/contrib/{r_version}/PACKAGES.gz")
@app.get("/bin/windows/contrib/{r_version}/PACKAGES.rds")
@app.get("/bin/macosx/contrib/{r_version}/PACKAGES")
@app.get("/bin/macosx/contrib/{r_version}/PACKAGES.gz")
@app.get("/bin/macosx/contrib/{r_version}/PACKAGES.rds")
async def serve_packages_file(request: Request, r_version: str = None):
    try:
        url_path = request.url.path.lstrip('/')
        file_path = f"r-packages/{url_path}"
        
        print(f"Attempting to serve PACKAGES file from: {file_path}")

        if not os.path.exists(file_path):
            raise HTTPException(
                status_code=404, 
                detail=f"PACKAGES file not found at: {file_path}"
            )

        if file_path.endswith('.gz'):
            media_type = 'application/gzip'
        elif file_path.endswith('.rds'):
            media_type = 'application/octet-stream'
        else:
            media_type = 'text/plain'

        return FileResponse(
            file_path,
            media_type=media_type
        )
        
    except Exception as e:
        print(f"Error serving PACKAGES file: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/src/contrib/{file_name}")
@app.get("/bin/windows/contrib/{r_version}/{file_name}")
@app.get("/bin/macosx/contrib/{r_version}/{file_name}")
async def serve_package(
    request: Request,
    file_name: str,
    r_version: str = None,
    db: Session = Depends(get_db)
):
    try:
        if file_name in ["PACKAGES", "PACKAGES.gz", "PACKAGES.rds"]:
            raise HTTPException(status_code=404, detail="Use PACKAGES endpoint")
            
        url_path = request.url.path.lstrip('/')
        file_path = f"r-packages/{url_path}"
        
        parts = file_name.rsplit("_", 1)
        if len(parts) != 2:
            raise HTTPException(status_code=400, detail="Invalid file name format")
        
        package = parts[0]
        version = parts[1].split(".")[0]
        
        if "windows" in str(request.url):
            platform = "windows"
        elif "macosx" in str(request.url):
            platform = "macos"
        else:
            platform = "source"

        if not os.path.exists(file_path):
            raise HTTPException(
                status_code=404, 
                detail=f"Package file not found: {file_path}"
            )

        today = date.today()
        download = db.query(Download).filter(
            Download.package == package,
            Download.date == today,
            Download.platform == platform
        ).first()
        
        if not download:
            download = Download(
                package=package,
                date=today,
                count=1,
                platform=platform
            )
            db.add(download)
        else:
            db.query(Download).filter(
                Download.id == download.id
            ).update(
                {"count": Download.count + 1},
                synchronize_session=False
            )
        
        db.commit()
        
        print(f"Package download: {package} {version} for {platform}")
        
        return FileResponse(
            file_path,
            filename=file_name,
            media_type="application/octet-stream"
        )
        
    except Exception as e:
        print(f"Error serving package: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/downloads", response_class=HTMLResponse)
async def get_downloads(request: Request, db: Session = Depends(get_db)):
    try:
        monthly_downloads = db.execute(
            text("""
                SELECT 
                    package,
                    DATE_TRUNC('month', date) as month,
                    platform,
                    SUM(count) as total_count
                FROM downloads
                GROUP BY package, DATE_TRUNC('month', date), platform
                ORDER BY DATE_TRUNC('month', date) DESC, package, platform
            """)
        ).fetchall()
        
        downloads_by_month = {}
        for row in monthly_downloads:
            month_str = row.month.strftime("%Y-%m")
            if month_str not in downloads_by_month:
                downloads_by_month[month_str] = {}
            
            if row.package not in downloads_by_month[month_str]:
                downloads_by_month[month_str][row.package] = {
                    'total': 0,
                    'platforms': {}
                }
            
            downloads_by_month[month_str][row.package]['platforms'][row.platform] = row.total_count
            downloads_by_month[month_str][row.package]['total'] += row.total_count
        
        return templates.TemplateResponse(
            "downloads.html",
            {
                "request": request,
                "downloads_by_month": downloads_by_month,
                "year": datetime.now().year,
                "docs_urls": DOC_URLS
            }
        )
    except Exception as e:
        print(f"Error in get_downloads: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/packages", response_class=HTMLResponse)
async def get_packages(request: Request, db: Session = Depends(get_db)):
    try:
        packages = {}
        r_packages_dir = Path("r-packages")
        
        src_contrib = r_packages_dir / "src" / "contrib"
        if src_contrib.exists():
            for tar_gz in src_contrib.glob("*.tar.gz"):
                package_name = tar_gz.name.split("_")[0]
                version = tar_gz.name.split("_")[1].replace(".tar.gz", "")
                if package_name not in packages:
                    packages[package_name] = {
                        "package": package_name,
                        "version": version,
                        "platforms": {
                            "source": {
                                "status": "SUCCESS",
                                "build_time": datetime.fromtimestamp(tar_gz.stat().st_mtime).strftime("%Y-%m-%d %H:%M:%S")
                            }
                        }
                    }

        for r_version in ["4.2", "4.3", "4.4"]:
            win_dir = r_packages_dir / "bin" / "windows" / "contrib" / r_version
            if win_dir.exists():
                for zip_file in win_dir.glob("*.zip"):
                    package_name = zip_file.name.split("_")[0]
                    if package_name in packages:
                        packages[package_name]["platforms"]["windows"] = {
                            "status": "SUCCESS",
                            "build_time": datetime.fromtimestamp(zip_file.stat().st_mtime).strftime("%Y-%m-%d %H:%M:%S"),
                            "r_version": r_version
                        }

        for r_version in ["4.2", "4.3", "4.4"]:
            mac_dir = r_packages_dir / "bin" / "macosx" / "contrib" / r_version
            if mac_dir.exists():
                for tgz_file in mac_dir.glob("*.tgz"):
                    package_name = tgz_file.name.split("_")[0]
                    if package_name in packages:
                        packages[package_name]["platforms"]["macos"] = {
                            "status": "SUCCESS",
                            "build_time": datetime.fromtimestamp(tgz_file.stat().st_mtime).strftime("%Y-%m-%d %H:%M:%S"),
                            "r_version": r_version
                        }

        for json_file in r_packages_dir.glob("build_status_*.json"):
            with open(json_file) as f:
                build_info = json.load(f)
                platform = build_info.get("platform", "unknown")
                for pkg_name, pkg_info in build_info.get("packages", {}).items():
                    if pkg_name not in packages:
                        if pkg_name not in packages:
                            packages[pkg_name] = {
                                "package": pkg_name,
                                "version": "",
                                "platforms": {}
                            }
                        packages[pkg_name]["platforms"][platform] = {
                            "status": "FAILED",
                            "build_time": pkg_info.get("build_time", ""),
                            "error_message": "No package file found"
                        }

        return templates.TemplateResponse(
            "packages.html", 
            {
                "request": request, 
                "year": datetime.now().year,
                "packages": packages
            }
        )
    except Exception as e:
        print(f"Error in get_packages: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    host = os.environ.get("HOST", "0.0.0.0")
    uvicorn.run("main:app", host=host, port=port, log_level="info")
