from newspaper import Article
url = "https://www.newsx.com/business/stock-market-today-closing-bell-sensex-jumps-583-points-nifty-reclaims-25000-on-strong-sector-performance-87629/"
article = Article(url)
article.download()
article.parse()
print(article.text)