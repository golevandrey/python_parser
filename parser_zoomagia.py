# Импорты библиотек
import requests
from bs4 import BeautifulSoup
import json
import time
from datetime import datetime
import schedule
import logging
import os
from typing import Dict, List, Optional

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    filename='zoomagia_parser.log'
)

# Класс с основной логикой парсинга
class ZoomagiaParser:
    def __init__(self):
        self.base_url = "https://zoomagia.ru"
        self.sale_url = f"{self.base_url}/shop/sale"
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'ru-RU,ru;q=0.8,en-US;q=0.5,en;q=0.3',
            'Connection': 'keep-alive'
        }
        # Создание папки для хранения результатов
        os.makedirs('output', exist_ok=True)

    # Получение всех ссылок на товары из раздела распродаж
    def get_product_links(self) -> List[str]:
        """Get all product links from the sale page"""
        try:
            logging.info(f"Fetching product links from {self.sale_url}")
            response = requests.get(self.sale_url, headers=self.headers, timeout=30)
            response.raise_for_status()
            soup = BeautifulSoup(response.text, 'html.parser')
            
            product_links = []
           
            products = soup.select('.grid-product')
            
            for product in products:
                link = product.select_one('.title a')
                if link and link.get('href'):
                    full_url = link['href'] if link['href'].startswith('http') else self.base_url + link['href']
                    product_links.append(full_url)
            
            logging.info(f"Found {len(product_links)} product links")
            return product_links
        except Exception as e:
            logging.error(f"Error getting product links: {str(e)}")
            return []

    def parse_product(self, url: str) -> Optional[Dict]:
        """Parse individual product page"""
        try:
            logging.info(f"Parsing product: {url}")
            response = requests.get(url, headers=self.headers, timeout=30)
            response.raise_for_status()
            soup = BeautifulSoup(response.text, 'html.parser')

             # Парсинг одного товара по ссылке
            product_data = {
                'name': self._get_name(soup),
                'manufacturer': self._get_manufacturer(soup),
                'price': self._get_price(soup),
                'category': self._get_category(soup),
                'images': self._get_images(soup),
                'weight': self._get_weight(soup),
                'description': self._get_tab_content(soup, '#product-des'),
                'composition': self._get_tab_content(soup, '#product-composition'),
                'analysis': self._get_tab_content(soup, '#product-analysis'),
                'feeding_norm': self._get_tab_content(soup, '#product-feeding_rates'),
                'reviews': self._get_reviews(soup),
                'url': url,
                'parsed_date': datetime.now().isoformat()
            }

            
            for key, value in product_data.items():
                if isinstance(value, str) and not value.strip():
                    product_data[key] = None

            return product_data
        except Exception as e:
            logging.error(f"Error parsing product {url}: {str(e)}")
            return None

    def _get_name(self, soup: BeautifulSoup) -> str:
        """Extract product name"""
        # Пробуем получить название из заголовка страницы
        title = soup.find('title')
        if title:
            title_text = title.text.strip()
            # Убираем часть после тире, если она есть
            if '–' in title_text:
                return title_text.split('–')[0].strip()
        
        # Если не получилось, пробуем получить из h1
        h1 = soup.find('h1')
        if h1:
            return h1.text.strip()
        
        return ""

    def _get_manufacturer(self, soup: BeautifulSoup) -> str:
        """Extract manufacturer"""
        # Производитель указан в метаданных keywords
        meta = soup.find('meta', {'name': 'keywords'})
        if meta and meta.get('content'):
            content = meta['content'].strip()
            # Разделяем по запятой и берем последний элемент
            parts = [part.strip() for part in content.split(',')]
            # Фильтруем пустые значения
            parts = [part for part in parts if part]
            if parts:
                return parts[-1]
        
        # Если не нашли в метаданных, ищем в других местах
        brand_link = soup.select_one('.brand a')
        if brand_link:
            return brand_link.text.strip()
            
        return ""

    def _get_price(self, soup: BeautifulSoup) -> Dict[str, str]:
        """Extract price information"""
        price_data = {
            'old_price': '',
            'current_price': '',
            'discount': ''
        }
        
        # Находим блок с ценой
        price_block = soup.select_one('.packing-price-item')
        if price_block:
            # Получаем старую цену
            old_price = price_block.select_one('.price-del')
            if old_price:
                price_data['old_price'] = old_price.text.strip()
            
            # Получаем текущую цену (весь текст без старой цены)
            price_text = price_block.text.strip()
            if old_price:
                # Убираем старую цену и символ рубля из текста
                current_price = price_text.replace(old_price.text.strip(), '').replace('₽', '').strip()
                price_data['current_price'] = current_price
            
            # Получаем процент скидки
            discount_block = price_block.select_one('.price-customer-discount-badge')
            if discount_block:
                price_data['discount'] = discount_block.text.strip()
        
        return price_data

    def _get_category(self, soup: BeautifulSoup) -> str:
        """Extract category"""
        breadcrumbs = soup.select('.shop-head-menu li')
        if len(breadcrumbs) >= 2:
            # Берем предпоследний элемент (категория)
            category = breadcrumbs[-2].text.strip()
            if category:
                return category
        return ""

    def _get_images(self, soup: BeautifulSoup) -> List[str]:
        """Extract product images"""
        images = []
        # Основное изображение
        main_image = soup.select_one('.simpleLens-big-image')
        if main_image and main_image.get('src'):
            images.append(main_image['src'])
        
        # Дополнительные изображения
        for img in soup.select('.simpleLens-thumbnails-container img'):
            src = img.get('src')
            if src and src not in images:
                images.append(src)
        
        return images

    def _get_weight(self, soup: BeautifulSoup) -> List[str]:
        """Extract available weights"""
        weights = []
        for weight_item in soup.select('.product-show-packing'):
            weight = weight_item.text.strip()
            if weight:
                weights.append(weight)
        return weights

    def _get_tab_content(self, soup: BeautifulSoup, tab_id: str) -> str:
        """Extract content from specified tab"""
        tab = soup.select_one(f'{tab_id}')
        if tab:
            # Удаляем все script и style теги
            for element in tab.select('script, style'):
                element.decompose()
            return tab.get_text(strip=True, separator='\n')
        return ""

    def _get_reviews(self, soup: BeautifulSoup) -> List[Dict]:
        """Extract product reviews"""
        reviews = []
        review_items = soup.select('.product-comments-block li')
        
        for review in review_items:
            review_data = {
                'text': review.get_text(strip=True)
            }
            reviews.append(review_data)
        
        return reviews

    def save_to_json(self, data: List[Dict], filename: str = 'output/zoomagia_products.json'):
        """Save parsed data to JSON file with timestamp"""
        try:
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            filename_with_timestamp = f"output/zoomagia_products_{timestamp}.json"
            
            with open(filename_with_timestamp, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            
            with open(filename, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
                
            logging.info(f"Data successfully saved to {filename} and {filename_with_timestamp}")
        except Exception as e:
            logging.error(f"Error saving data to JSON: {str(e)}")

    def run_parser(self):
        """Main method to run the parser"""
        logging.info("Starting parser run")
        product_links = self.get_product_links()
        products_data = []

        for i, link in enumerate(product_links):
            logging.info(f"Processing product {i+1}/{len(product_links)}: {link}")
            product_data = self.parse_product(link)
            if product_data:
                products_data.append(product_data)
            time.sleep(2)  # Не перегружаем сервер)

        if products_data:
            self.save_to_json(products_data)
            logging.info(f"Parser run completed. Processed {len(products_data)} products")
        else:
            logging.warning("No products were successfully parsed")

def main():
    parser = ZoomagiaParser()
    
    # Парсим каждые семь дней
    schedule.every(7).days.do(parser.run_parser)
    
    parser.run_parser()
    
    while True:
        schedule.run_pending()
        time.sleep(3600)  # Проверяем каждый час не прошло ли 7 дней

if __name__ == "__main__":
    main()