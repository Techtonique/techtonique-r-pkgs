# techtonique-r-pkgs

Lives at [https://r-packages.techtonique.net/](https://r-packages.techtonique.net/)

## How to add a new package

Add the package to the `packages.json` file.

---

## 📊 Download Badge API

### Quick Start - Adding Badges to Your Packages

Add download badges to your package READMEs:

```markdown
<!-- Monthly Downloads -->
![Downloads](https://r-packages.techtonique.net/badges/downloads/last-month/yourpackage.svg)

<!-- Total Downloads -->
![Total Downloads](https://r-packages.techtonique.net/badges/downloads/grand-total/yourpackage.svg?color=brightgreen)
```

**Replace `yourpackage` with your actual package name.**

### Badge Endpoint

```
GET /badges/downloads/{period}/{package}.svg?color={color}
```

**Periods:** `last-day`, `last-week`, `last-month`, `grand-total`  
**Colors:** `blue`, `green`, `brightgreen`, `orange`, `red`, `yellow`, `yellowgreen`, `lightgrey`, `auto`

### Examples

```markdown
<!-- Basic badge -->
![](https://r-packages.techtonique.net/badges/downloads/last-month/ggplot2.svg)

<!-- With custom color -->
![](https://r-packages.techtonique.net/badges/downloads/grand-total/dplyr.svg?color=brightgreen)

<!-- Auto color (adjusts based on download count) -->
![](https://r-packages.techtonique.net/badges/downloads/last-week/tidyr.svg?color=auto)

<!-- Clickable badge -->
[![Total Downloads](https://r-packages.techtonique.net/badges/downloads/grand-total/yourpackage.svg?color=auto)](https://r-packages.techtonique.net)
```

### JSON API Endpoints

**Total downloads (CRAN logs compatible):**
```bash
curl https://r-packages.techtonique.net/downloads/total/last-week/yourpackage
```

**Daily breakdown:**
```bash
curl "https://r-packages.techtonique.net/downloads/daily/yourpackage?from_date=2024-11-01&to_date=2024-12-01"
```

### Using in R

```r
library(httr)
library(jsonlite)

# Get total downloads
url <- "https://r-packages.techtonique.net/downloads/total/last-month/yourpackage"
response <- GET(url)
data <- fromJSON(content(response, "text"))
print(data)
```

### Auto Color Thresholds

When using `color=auto`, badges automatically adjust:
- 🟢 **brightgreen** → 100,000+ downloads
- 🟢 **green** → 10,000+ downloads
- 🟡 **yellowgreen** → 1,000+ downloads
- 🔵 **blue** → 100+ downloads
- ⚪ **lightgrey** → < 100 downloads

### Technical Notes

- Badges cached for 1 hour
- Numbers formatted automatically (1.2k, 1.2M)
- Error badge shown if package not found
- All endpoints query the existing downloads database
