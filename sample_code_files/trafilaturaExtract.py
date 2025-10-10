from trafilatura import fetch_url, extract, html2txt
downloaded = fetch_url('https://www.newsx.com/business/stock-market-today-closing-bell-sensex-jumps-583-points-nifty-reclaims-25000-on-strong-sector-performance-87629/')
# downloaded = fetch_url('https://www.lokmattimes.com/business/sensex-rises-583-points-nifty-tops-25000-as-it-banking-stocks-lead-rally/')
result = extract(downloaded)
# result = html2txt(downloaded)
print(result)

