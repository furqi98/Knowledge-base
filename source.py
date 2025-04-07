import os
import json
import re
import time
import hashlib
import urllib.parse
from urllib.robotparser import RobotFileParser
from bs4 import BeautifulSoup
import requests
from collections import defaultdict

class KnowledgeBaseGenerator:
    def __init__(self, output_file="knowledge_base.json", max_pages_per_domain=50, delay=1, respect_robots=False, content_only=True):
        self.knowledge_base = {}
        self.visited_urls = set()
        self.output_file = output_file
        self.max_pages_per_domain = max_pages_per_domain  # Now represents content page limit
        self.delay = delay  # Delay between requests in seconds
        self.robot_parsers = {}  # Cache for robot.txt parsers
        self.respect_robots = respect_robots  # Whether to respect robots.txt
        self.content_only = content_only  # Whether to only crawl content-rich pages
        self.error_urls = []  # Track URLs with errors
        self.stats = {
            "pages_crawled": 0,
            "pages_skipped": 0,
            "errors": 0
        }
        # Define content-rich page types to focus on
        self.content_page_types = {
            "article", "blog", "news", "resource", "guide", "faq", 
            "research", "publication", "study", "report"
        }
        # Define page types to avoid
        self.avoid_page_types = {
            "login", "register", "signup", "signin", "account", 
            "cart", "checkout", "contact", "about", "team", "privacy", 
            "terms", "policy", "legal", "copyright", "search"
        }

    def is_allowed_by_robots(self, url):
        """Check if the URL is allowed by robots.txt"""
        # Ignore robots.txt rules by always returning True
        if not self.respect_robots:
            return True
        
        parsed_url = urllib.parse.urlparse(url)
        domain = f"{parsed_url.scheme}://{parsed_url.netloc}"
        
        if domain not in self.robot_parsers:
            robots_url = f"{domain}/robots.txt"
            parser = RobotFileParser()
            parser.set_url(robots_url)
            try:
                parser.read()
                self.robot_parsers[domain] = parser
            except Exception as e:
                print(f"Error parsing robots.txt for {domain}: {e}")
                # If we can't parse robots.txt, we'll assume it's allowed
                return True
        
        is_allowed = self.robot_parsers[domain].can_fetch("*", url)
        if not is_allowed:
            self.stats["pages_skipped"] += 1
            
        return is_allowed

    def get_domain(self, url):
        """Extract the domain from a URL"""
        parsed_url = urllib.parse.urlparse(url)
        return parsed_url.netloc

    def normalize_url(self, url, base_url):
        """Normalize the URL and make it absolute if it's relative"""
        # Remove fragments
        url = url.split('#')[0]
        
        # Handle relative URLs
        if not url.startswith(('http://', 'https://')):
            return urllib.parse.urljoin(base_url, url)
        
        return url

    def clean_url(self, url):
        """Clean the URL by removing tracking and unnecessary parameters"""
        # Parse the URL
        parsed_url = urllib.parse.urlparse(url)
        
        # For alz.org, completely strip all query parameters as they're duplicates
        if parsed_url.netloc == "www.alz.org":
            clean_url = urllib.parse.urlunparse((
                parsed_url.scheme,
                parsed_url.netloc,
                parsed_url.path,
                parsed_url.params,
                '',  # No query
                ''   # No fragment
            ))
            return clean_url
        
        # For WebMD, preserve pagination parameters but remove others
        if parsed_url.netloc == "www.webmd.com":
            query_params = urllib.parse.parse_qs(parsed_url.query)
            # Keep only pagination parameters
            filtered_params = {k: v for k, v in query_params.items() if k == 'pg'}
            filtered_query = urllib.parse.urlencode(filtered_params, doseq=True)
            
            clean_url = urllib.parse.urlunparse((
                parsed_url.scheme,
                parsed_url.netloc,
                parsed_url.path,
                parsed_url.params,
                filtered_query,
                ''  # No fragment
            ))
            return clean_url
        
        # List of common tracking parameters to remove
        tracking_params = [
            'utm_source', 'utm_medium', 'utm_campaign', 'utm_term', 'utm_content',
            'fbclid', 'gclid', 'msclkid', 'ref', 'source', 'intcmp', 'cmp', 'mc_cid', 
            'mc_eid', 'sb_referer_host', '_hsenc', '_hsmi', '_ga', 'form', 'lang'
        ]
        
        # Parse query parameters
        query_params = urllib.parse.parse_qs(parsed_url.query)
        
        # Remove tracking parameters
        filtered_params = {k: v for k, v in query_params.items() if k.lower() not in tracking_params}
        
        # Rebuild the query string
        filtered_query = urllib.parse.urlencode(filtered_params, doseq=True)
        
        # Rebuild the URL
        clean_url = urllib.parse.urlunparse((
            parsed_url.scheme,
            parsed_url.netloc,
            parsed_url.path,
            parsed_url.params,
            filtered_query,
            ''  # No fragment
        ))
        
        return clean_url

    def is_internal_link(self, url, base_domain):
        """Check if the URL is an internal link (same domain)"""
        url_domain = self.get_domain(url)
        return url_domain == base_domain or url_domain == f"www.{base_domain}" or f"www.{url_domain}" == base_domain

    def site_specific_content_extraction(self, soup, url):
        """Apply site-specific content extraction based on website analysis"""
        domain = self.get_domain(url)
        
        # Get specific content container based on domain
        main_content = None
        
        if domain == "www.caregiveraction.org":
            # For caregiveraction.org, content is in #main or #content
            main_content = soup.find(id="main") or soup.find(id="content")
            
        elif domain == "www.asaging.org":
            # For asaging.org, content is in .content .block-content
            content_elements = soup.select(".content .block-content, .content .content-full")
            if content_elements:
                main_content = content_elements[0]
                
        elif domain == "www.webmd.com":
            # For webmd.com, content is in #global-main
            main_content = soup.find(id="global-main") or soup.select_one(".resp-2-col-rr, .article.medref")
            
        elif domain == "www.aarp.org":
            # For aarp.org, content is in complex nested containers
            main_content = soup.select_one(".uxdia-o-article-rail") or soup.select_one(".container .responsivegrid")
            
        elif domain == "www.nia.nih.gov":
            # For nia.nih.gov, content is in .main-content .clearfix
            main_content = soup.select_one(".main-content .clearfix") or soup.find(id="main-content")
            
        elif domain == "www.alz.org":
            # For alz.org, content is in .tab-content or #content
            main_content = soup.select_one(".tab-content") or soup.find(id="content")
            
        elif domain == "www.ncoa.org":
            # For ncoa.org, content is in #content
            main_content = soup.find(id="content") or soup.select_one(".styles_container__HFOo5")
            
        elif domain == "www.seniorliving.org":
            # For seniorliving.org, content is in .main-content
            main_content = soup.select_one(".main-content")
        
        return main_content

    def site_specific_link_filtering(self, links, base_domain):
        """Apply site-specific link filtering based on website analysis"""
        content_links = []
        other_links = []
        
        for link in links:
            href = link['href'].strip()
            
            # Skip empty links and javascript
            if not href or href.startswith(('javascript:', 'mailto:', 'tel:')):
                continue
                
            lower_href = href.lower()
            
            # Site-specific filtering
            if base_domain == "www.caregiveraction.org":
                # Prioritize toolbox content first, then other content sections
                if '/toolbox/' in lower_href:
                    content_links.insert(0, href)  # Insert at the beginning to prioritize
                elif any(pattern in lower_href for pattern in ['/corporate-partners/', '/caregiver-story/', '/guide/', '/blueprint-', '/hipaa-', '/stroke', '/traumatic-brain-injury/', '/ptsd/', '/lighting-your-way/']):
                    content_links.append(href)
                else:
                    other_links.append(href)
                    
            elif base_domain == "www.asaging.org":
                # Most links are content
                content_links.append(href)
                
            elif base_domain == "www.webmd.com":
                # Prioritize a-to-z-guides, diet/news, guide
                if any(pattern in lower_href for pattern in ['/a-to-z-guides/', '/diet/news/', '/guide/']):
                    content_links.append(href)
                else:
                    other_links.append(href)
                    
            elif base_domain == "www.aarp.org":
                # Prioritize caregiving content
                if '/caregiving/' in lower_href:
                    content_links.append(href)
                else:
                    other_links.append(href)
                    
            elif base_domain == "www.nia.nih.gov":
                # Prioritize research content
                if '/research/' in lower_href:
                    content_links.append(href)
                else:
                    other_links.append(href)
                    
            elif base_domain == "www.alz.org":
                # Prioritize blog and help-support
                if any(pattern in lower_href for pattern in ['/blog/', '/help-support/']):
                    content_links.append(href)
                else:
                    other_links.append(href)
                    
            elif base_domain == "www.ncoa.org":
                # Prioritize older-adults content
                if '/older-adults/' in lower_href or '/caregivers/' in lower_href:
                    content_links.append(href)
                else:
                    other_links.append(href)
                    
            elif base_domain == "www.seniorliving.org":
                # Most content is articles
                if any(pattern in lower_href for pattern in ['/care/', '/health/', '/finance/']):
                    content_links.append(href)
                else:
                    other_links.append(href)
                    
            else:
                # Default behavior for other domains
                if any(content_word in lower_href for content_word in ['article', 'post', 'blog', 'news', 'resource']):
                    content_links.append(href)
                else:
                    other_links.append(href)
        
        return content_links, other_links

    def extract_text_with_structure(self, soup, url=""):
        """Extract text content with structural information, focusing on main content"""
        content = {
            "title": "",
            "meta_description": "",
            "headings": {},
            "paragraphs": [],
            "lists": []
        }
        
        # Extract page title
        title_tag = soup.find('title')
        if title_tag and title_tag.string:
            title_text = title_tag.string.strip()
            # Clean up title by removing site name if present
            site_indicators = [" - AARP", " | WebMD", " | Mayo Clinic", " | NIH", " | CDC"]
            for indicator in site_indicators:
                if indicator in title_text:
                    title_text = title_text.split(indicator)[0].strip()
            content["title"] = title_text
        
        # Extract meta description
        meta_desc = soup.find('meta', attrs={'name': 'description'})
        if meta_desc and meta_desc.get('content'):
            content["meta_description"] = meta_desc['content'].strip()
        
        # Get site-specific content container
        main_content = self.site_specific_content_extraction(soup, url)
        
        # If no specific content found, use the standard approach
        if not main_content:
            # Look for common content containers
            content_containers = [
                soup.find('article'),
                soup.find(id=re.compile(r'(content|main|article|post)', re.I)),
                soup.find(class_=re.compile(r'(content|main|article|post)', re.I)),
                soup.find('main'),
                soup.find(attrs={"role": "main"}),
                soup.find(attrs={"itemprop": "articleBody"})
            ]
            
            # Use the first valid container found
            for container in content_containers:
                if container:
                    main_content = container
                    break
        
        # If no main content found, use the whole body
        if not main_content:
            main_content = soup.body
        
        # Remove common elements that aren't part of the main content
        if main_content:
            # Find and remove navigation
            for nav in main_content.find_all(['nav', 'header', 'footer', 'aside']):
                nav.decompose()
                
            # Remove ads, sharing, and other non-content elements
            for elem in main_content.find_all(class_=re.compile(r'(nav|menu|sidebar|banner|ad|share|comment|footer|promo)', re.I)):
                elem.decompose()
                
            # Remove script and style tags
            for elem in main_content.find_all(['script', 'style', 'noscript', 'iframe']):
                elem.decompose()
        
        # If we're working with a main content element, update our source
        soup_to_process = main_content if main_content else soup
        
        # Extract headings
        for level in range(1, 7):
            heading_tags = soup_to_process.find_all(f'h{level}')
            if heading_tags:
                content["headings"][f"h{level}"] = []
                for tag in heading_tags:
                    # Skip navigational headings
                    heading_text = tag.get_text().strip()
                    if len(heading_text) > 3 and not re.match(r'^(menu|navigation|search|related|popular|more)$', heading_text.lower()):
                        content["headings"][f"h{level}"].append(heading_text)
        
        # Extract paragraphs (excluding very short/navigational ones)
        extracted_texts = set()  # To avoid duplicates
        for p in soup_to_process.find_all('p'):
            text = p.get_text().strip()
            # Filter out short texts, template variables, and navigation items
            if (text and len(text) > 20 and 
                '%{' not in text and 
                not re.search(r'(login|sign in|subscribe|newsletter|privacy policy|terms)', text.lower()) and
                not re.match(r'^(you are now leaving|already a member)', text.lower()) and
                text not in extracted_texts):
                
                # Remove any remaining placeholders or special patterns
                text = re.sub(r'%\{[^}]+\}%', '', text)
                text = re.sub(r'ARTICLE CONTINUES AFTER ADVERTISEMENT', '', text)
                
                if text.strip() and not text.strip().lower() in extracted_texts:
                    content["paragraphs"].append(text.strip())
                    extracted_texts.add(text.strip().lower())
        
        # Extract lists (excluding navigational ones)
        for list_type in ['ul', 'ol']:
            for list_elem in soup_to_process.find_all(list_type):
                # Skip lists in navigational elements
                if list_elem.parent and list_elem.parent.name in ['nav', 'header', 'footer', 'aside']:
                    continue
                    
                # Check if the list is likely a navigation menu
                classes = list_elem.get('class', [])
                if classes and any('menu' in c.lower() or 'nav' in c.lower() for c in classes):
                    continue
                
                list_items = []
                for item in list_elem.find_all('li'):
                    text = item.get_text().strip()
                    # Filter similarly to paragraphs
                    if (text and len(text) > 5 and 
                        '%{' not in text and 
                        not re.search(r'(login|sign in|subscribe|newsletter)', text.lower())):
                        
                        # Remove any remaining placeholders or special patterns
                        text = re.sub(r'%\{[^}]+\}%', '', text)
                        
                        if text.strip():
                            list_items.append(text.strip())
                
                if list_items:
                    # Ensure list items aren't just menu items
                    if not all(len(item) < 20 for item in list_items):
                        content["lists"].append({
                            "type": list_type,
                            "items": list_items
                        })
        
        # Add the URL for reference
        if url:
            content["url"] = url
            
        return content

    def classify_page(self, url, base_url, soup=None):
        """Classify the page type based on URL structure and optionally content"""
        # Remove the base URL to analyze the path
        path = url.replace(base_url, "").strip("/")
        
        if not path:
            return "homepage"

        # Check for login, account, and other avoid pages in URL
        if any(avoid in path.lower() for avoid in self.avoid_page_types):
            for avoid in self.avoid_page_types:
                if re.search(rf'\b{avoid}s?\b', path.lower()):
                    return avoid
            
        # Common patterns for content-rich pages
        if re.search(r'(article|post|blog)s?/', path, re.I):
            return "article"
        elif re.search(r'(news|press|release)s?/', path, re.I):
            return "news"
        elif re.search(r'(resource|guide|handbook|help)s?/', path, re.I):
            return "resource"
        elif re.search(r'(faq|question|answer)s?/?', path, re.I):
            return "faq"
        elif re.search(r'(research|publication|study|report)s?/', path, re.I):
            return "research"
        
        # Check content if soup is provided for better classification
        if soup:
            # Check if there are many paragraphs (likely an article)
            paragraphs = soup.find_all('p')
            if len(paragraphs) > 5:
                text_length = sum(len(p.get_text()) for p in paragraphs)
                if text_length > 1000:  # More than 1000 characters of text
                    return "article"
            
            # Check for article schema or metadata
            article_schema = soup.find('article') or soup.find(attrs={"itemtype": re.compile("Article")})
            if article_schema:
                return "article"
                
            # Check for common content section class names
            content_classes = ["content", "article", "post", "blog", "entry", "main-content"]
            for content_class in content_classes:
                if soup.find(class_=re.compile(content_class, re.I)):
                    return "article"
        
        # If no specific pattern matches, use the first directory in the path
        if '/' in path:
            category = path.split('/')[0]
            return category
        
        return "other"
    
    def is_content_rich_page(self, page_type, soup=None):
        """Determine if a page is likely to contain valuable content based on its type and content"""
        # Check if the page type is in our content-rich types
        if page_type.lower() in self.content_page_types:
            return True
            
        # Check if the page type is in our avoid types
        if page_type.lower() in self.avoid_page_types:
            return False
            
        # For other pages, analyze the content if soup is provided
        if soup:
            # Count paragraphs and estimate text length
            paragraphs = soup.find_all('p')
            if len(paragraphs) > 5:
                text_length = sum(len(p.get_text()) for p in paragraphs)
                if text_length > 1000:  # More than 1000 characters of text
                    return True
                    
            # Check for structured content like lists
            lists = soup.find_all(['ul', 'ol'])
            if len(lists) > 2:
                return True
        
        # Default for unknown page types
        return True if page_type == "homepage" else False

    def should_crawl_domain(self, domain):
        """Check if we should continue crawling this domain based on content page count"""
        # Get current page count for this domain
        if domain not in self.knowledge_base:
            return True
            
        # Count total pages for this domain
        domain_pages_count = len(self.knowledge_base[domain]["pages"])
        
        # Count content-rich pages for this domain
        content_pages_count = 0
        for url, page_data in self.knowledge_base[domain]["pages"].items():
            if page_data["type"].lower() in self.content_page_types:
                content_pages_count += 1
                
        # If we've reached content page limit, stop crawling
        if content_pages_count >= self.max_pages_per_domain:
            return False
            
        # If we've reached overall page limit and it's very high (3x content limit),
        # stop to prevent crawling indefinitely
        if domain_pages_count >= self.max_pages_per_domain * 3:
            return False
            
        # Otherwise continue crawling
        return True

    def crawl_page(self, url, base_url, base_domain, depth=0):
        """Crawl a single page and extract knowledge"""
        # Clean URL by removing tracking parameters
        clean_url = self.clean_url(url)
        
        if clean_url in self.visited_urls:
            return
            
        # Use the clean URL for processing
        url = clean_url
        
        # Check if domain limit is reached
        domain = self.get_domain(url)
        if not self.should_crawl_domain(domain):
            print(f"Skipping {url} (reached max pages for domain {domain})")
            self.stats["pages_skipped"] += 1
            return
        
        # Respect robots.txt
        if not self.is_allowed_by_robots(url):
            print(f"Skipping {url} (disallowed by robots.txt)")
            return
        
        # Add to visited URLs to avoid revisiting
        self.visited_urls.add(url)
        
        try:
            # Add delay to be respectful
            time.sleep(self.delay)
            
            # Send request with a realistic user agent
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
                'Accept-Language': 'en-US,en;q=0.5',
                'Referer': base_url,
                'DNT': '1',
                'Connection': 'keep-alive',
                'Upgrade-Insecure-Requests': '1',
            }
            
            response = requests.get(url, headers=headers, timeout=10)
            if response.status_code != 200:
                error_msg = f"Failed to fetch {url}: Status code {response.status_code}"
                print(error_msg)
                self.error_urls.append({"url": url, "error": error_msg, "status_code": response.status_code})
                self.stats["errors"] += 1
                return
            
            content_type = response.headers.get('Content-Type', '')
            if 'text/html' not in content_type.lower():
                print(f"Skipping non-HTML content: {url}")
                self.stats["pages_skipped"] += 1
                return
            
            soup = BeautifulSoup(response.text, 'html.parser')
            
            # Classify the page with content analysis
            page_type = self.classify_page(url, base_url, soup)
            
            # Skip pages that aren't content-rich unless they're the homepage (if content_only is enabled)
            if self.content_only and not self.is_content_rich_page(page_type, soup) and page_type != "homepage":
                print(f"Skipping {url} (not content-rich, type: {page_type})")
                self.stats["pages_skipped"] += 1
                return
            
            # Extract content
            content = self.extract_text_with_structure(soup, url)
            
            # Add content to knowledge base
            domain = self.get_domain(base_url)
            if domain not in self.knowledge_base:
                self.knowledge_base[domain] = {
                    "base_url": base_url, 
                    "pages": {},
                    "stats": {
                        "pages_crawled": 0,
                        "by_type": {}
                    }
                }
            
            # Check again if we've hit the limit for this domain
            if not self.should_crawl_domain(domain):
                print(f"Skipping adding {url} (reached max pages for domain {domain})")
                self.stats["pages_skipped"] += 1
                return
            
            self.knowledge_base[domain]["pages"][url] = {
                "type": page_type,
                "content": content,
                "depth": depth,
                "crawled_at": time.strftime("%Y-%m-%d %H:%M:%S")
            }
            
            # Update statistics
            self.stats["pages_crawled"] += 1
            self.knowledge_base[domain]["stats"]["pages_crawled"] += 1
            
            # Update page type statistics
            if page_type not in self.knowledge_base[domain]["stats"]["by_type"]:
                self.knowledge_base[domain]["stats"]["by_type"][page_type] = 0
            self.knowledge_base[domain]["stats"]["by_type"][page_type] += 1
            
            # Calculate content page count
            content_pages_count = sum(
                count for p_type, count in self.knowledge_base[domain]["stats"]["by_type"].items() 
                if p_type.lower() in self.content_page_types
            )
            
            if page_type.lower() in self.content_page_types:
                print(f"Crawled {url} (Type: {page_type}) [Content page {content_pages_count}/{self.max_pages_per_domain}]")
            else:
                print(f"Crawled {url} (Type: {page_type})")
            
            # Check if we should continue crawling this domain
            if not self.should_crawl_domain(domain):
                # Count content pages
                content_pages = sum(
                    count for p_type, count in self.knowledge_base[domain]["stats"]["by_type"].items() 
                    if p_type.lower() in self.content_page_types
                )
                
                if content_pages >= self.max_pages_per_domain:
                    print(f"Reached target of {self.max_pages_per_domain} content pages for domain {domain}")
                else:
                    print(f"Reached maximum total pages while searching for content for domain {domain}")
                return
            
            # Find links to crawl next
            links = soup.find_all('a', href=True)
            
            # Apply site-specific link filtering
            content_links, other_links = [], []
            
            for link in links:
                href = link['href'].strip()
                
                # Skip empty links and javascript
                if not href or href.startswith(('javascript:', 'mailto:', 'tel:')):
                    continue
                
                # Normalize URL
                next_url = self.normalize_url(href, url)
                
                # Skip already visited URLs
                if next_url in self.visited_urls:
                    continue
                
                # Only follow internal links
                if self.is_internal_link(next_url, base_domain):
                    lower_href = next_url.lower()
                    
                    # Site-specific filtering
                    if base_domain == "www.caregiveraction.org":
                        # Prioritize toolbox content first, then other content sections
                        if '/toolbox/' in lower_href:
                            content_links.insert(0, next_url)  # Insert at the beginning to prioritize
                        elif any(pattern in lower_href for pattern in ['/corporate-partners/', '/caregiver-story/', '/guide/', '/blueprint-', '/hipaa-', '/stroke', '/traumatic-brain-injury/', '/ptsd/', '/lighting-your-way/']):
                            content_links.append(next_url)
                        else:
                            other_links.append(next_url)
                            
                    elif base_domain == "www.asaging.org":
                        # Most links are content
                        content_links.append(next_url)
                        
                    elif base_domain == "www.webmd.com":
                        # Prioritize a-to-z-guides, diet/news, guide
                        if any(pattern in lower_href for pattern in ['/a-to-z-guides/', '/diet/news/', '/guide/']):
                            content_links.append(next_url)
                        else:
                            other_links.append(next_url)
                            
                    elif base_domain == "www.aarp.org":
                        # Prioritize caregiving content
                        if '/caregiving/' in lower_href:
                            content_links.append(next_url)
                        else:
                            other_links.append(next_url)
                            
                    elif base_domain == "www.nia.nih.gov":
                        # Prioritize research content
                        if '/research/' in lower_href:
                            content_links.append(next_url)
                        else:
                            other_links.append(next_url)
                            
                    elif base_domain == "www.alz.org":
                        # Prioritize blog and help-support
                        if any(pattern in lower_href for pattern in ['/blog/', '/help-support/']):
                            content_links.append(next_url)
                        else:
                            other_links.append(next_url)
                            
                    elif base_domain == "www.ncoa.org":
                        # Prioritize older-adults content
                        if '/older-adults/' in lower_href or '/caregivers/' in lower_href:
                            content_links.append(next_url)
                        else:
                            other_links.append(next_url)

                    elif base_domain == "www.seniorliving.org":
                       # Most content is articles
                       if any(pattern in lower_href for pattern in ['/care/', '/health/', '/finance/']):
                           content_links.append(next_url)
                       else:
                           other_links.append(next_url)
                           
                    else:
                       # Default behavior for other domains
                       if any(content_word in lower_href for content_word in ['article', 'post', 'blog', 'news', 'resource']):
                           content_links.append(next_url)
                       else:
                           other_links.append(next_url)
           
           # Crawl content-rich links first
            for next_url in content_links:
               if self.should_crawl_domain(domain):
                   self.crawl_page(next_url, base_url, base_domain, depth + 1)
           
           # Then crawl other potentially useful links
            for next_url in other_links:
               if self.should_crawl_domain(domain):
                   self.crawl_page(next_url, base_url, base_domain, depth + 1)
           
        except Exception as e:
           error_msg = f"Error crawling {url}: {str(e)}"
           print(error_msg)
           self.error_urls.append({"url": url, "error": error_msg, "exception": str(e)})
           self.stats["errors"] += 1
   
    def crawl_website(self, url):
       """Crawl a website starting from the given URL"""
       # Normalize the starting URL
       if not url.endswith('/'):
           url += '/'
       
       start_time = time.time()
       print(f"\n{'='*50}")
       print(f"Starting crawl of {url}")
       print(f"{'='*50}")
       
       parsed_url = urllib.parse.urlparse(url)
       base_url = f"{parsed_url.scheme}://{parsed_url.netloc}"
       base_domain = self.get_domain(url)
       
       # Reset domain-specific stats
       if base_domain in self.knowledge_base:
           self.knowledge_base[base_domain]["stats"] = {
               "pages_crawled": 0,
               "by_type": {}
           }
       
       self.crawl_page(url, base_url, base_domain, depth=0)
       
       end_time = time.time()
       elapsed = end_time - start_time
       
       print(f"\n{'='*50}")
       print(f"Completed crawl of {url}")
       print(f"Time elapsed: {elapsed:.2f} seconds")
       
       if base_domain in self.knowledge_base:
           pages_crawled = self.knowledge_base[base_domain]["stats"]["pages_crawled"]
           print(f"Pages crawled: {pages_crawled}")
           
           if "by_type" in self.knowledge_base[base_domain]["stats"]:
               # Count content pages
               content_pages = sum(
                   count for p_type, count in self.knowledge_base[base_domain]["stats"]["by_type"].items() 
                   if p_type.lower() in self.content_page_types
               )
               print(f"Content pages: {content_pages}/{self.max_pages_per_domain}")
               
               print("Pages by type:")
               for page_type, count in self.knowledge_base[base_domain]["stats"]["by_type"].items():
                   is_content = page_type.lower() in self.content_page_types
                   print(f"  - {page_type}: {count}" + (" (content)" if is_content else ""))
                   
       print(f"{'='*50}\n")
       
       return self.knowledge_base.get(base_domain, {})
   
    def crawl_websites(self, urls):
       """Crawl multiple websites"""
       for url in urls:
           self.crawl_website(url)
       
       # Post-process the knowledge base
       self.remove_duplicate_content()
           
       # Save the knowledge base
       self.save_knowledge_base()
       
       return self.knowledge_base
   
    def save_knowledge_base(self):
       """Save the knowledge base to a JSON file"""
       with open(self.output_file, 'w', encoding='utf-8') as f:
           json.dump(self.knowledge_base, f, indent=2, ensure_ascii=False)
       
       print(f"Knowledge base saved to {self.output_file}")
   
    def add_metadata(self):
       """Add metadata about the crawl to the knowledge base"""
       total_errors = len(self.error_urls)
       
       metadata = {
           "generator": "KnowledgeBaseGenerator",
           "generated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
           "statistics": {
               "total_domains": len(self.knowledge_base) - (1 if "_metadata" in self.knowledge_base else 0),
               "total_pages": sum(len(domain_data["pages"]) for domain_data in self.knowledge_base.values() if isinstance(domain_data, dict) and "pages" in domain_data),
               "pages_crawled": self.stats["pages_crawled"],
               "pages_skipped": self.stats["pages_skipped"],
               "errors": self.stats["errors"]
           },
           "errors": self.error_urls[:100]  # Include up to 100 errors for debugging
       }
       
       self.knowledge_base["_metadata"] = metadata
   
    def remove_duplicate_content(self):
       """Remove duplicate paragraphs and content across pages"""
       # Track paragraphs by hash to identify duplicates
       paragraph_hashes = {}
       duplicates_removed = 0
       
       # Process each domain
       for domain, domain_data in self.knowledge_base.items():
           if domain == "_metadata":
               continue
               
           for url, page_data in domain_data["pages"].items():
               if "content" in page_data and "paragraphs" in page_data["content"]:
                   unique_paragraphs = []
                   
                   for paragraph in page_data["content"]["paragraphs"]:
                       # Generate a hash of the paragraph text (after normalization)
                       # Normalize by lowercasing and removing extra whitespace
                       normalized_text = re.sub(r'\s+', ' ', paragraph.lower()).strip()
                       text_hash = hashlib.md5(normalized_text.encode()).hexdigest()
                       
                       # Only keep paragraphs we haven't seen before in this page
                       if text_hash not in paragraph_hashes:
                           paragraph_hashes[text_hash] = url
                           unique_paragraphs.append(paragraph)
                       elif paragraph_hashes[text_hash] != url:
                           # This is a true duplicate (across different pages)
                           # We still include it in the current page
                           unique_paragraphs.append(paragraph)
                       else:
                           # This is a duplicate within the same page
                           duplicates_removed += 1
                   
                   # Update page with unique paragraphs
                   page_data["content"]["paragraphs"] = unique_paragraphs
       
       print(f"Removed {duplicates_removed} duplicate paragraphs within pages")
   
    def generate_categories(self):
       """Generate a categorical view of the knowledge base"""
       categorical = defaultdict(lambda: defaultdict(list))
       
       for domain, domain_data in self.knowledge_base.items():
           if domain == "_metadata":
               continue
               
           for url, page_data in domain_data["pages"].items():
               page_type = page_data["type"]
               title = page_data["content"]["title"]
               categorical[domain][page_type].append({
                   "url": url,
                   "title": title
               })
       
       categorical_file = os.path.splitext(self.output_file)[0] + "_categories.json"
       with open(categorical_file, 'w', encoding='utf-8') as f:
           json.dump(categorical, f, indent=2, ensure_ascii=False)
       
       print(f"Categorical view saved to {categorical_file}")


def main():
   # List of websites to crawl
   websites = [
       "https://www.caregiveraction.org/toolbox/",  # Start from Toolbox page
       "https://www.asaging.org/",
       "https://www.webmd.com/",
       "https://www.relias.com/",
       "https://www.aarp.org/caregiving/",
       "https://www.nia.nih.gov/",
       "https://www.alz.org/",
       "https://www.ncoa.org/",
       "https://www.seniorliving.org/"
   ]
   
   # Parse command line arguments
   import argparse
   parser = argparse.ArgumentParser(description='Knowledge Base Generator')
   parser.add_argument('--output', '-o', type=str, default="caregiving_knowledge_base.json", help='Output JSON file')
   parser.add_argument('--max-pages', '-m', type=int, default=50, help='Maximum content-rich pages per domain')
   parser.add_argument('--delay', '-d', type=float, default=2.0, help='Delay between requests in seconds')
   parser.add_argument('--ignore-robots', '-i', action='store_true', help='Ignore robots.txt (default: True, will ignore robots.txt)')
   parser.add_argument('--respect-robots', '-r', action='store_true', help='Respect robots.txt')
   parser.add_argument('--sites', '-s', nargs='+', help='Specific sites to crawl (instead of default list)')
   parser.add_argument('--content-only', '-c', action='store_true', help='Crawl only content-rich pages (default: True)')
   parser.add_argument('--all-pages', '-a', action='store_true', help='Crawl all page types, not just content-rich ones')
   args = parser.parse_args()
   
   # Use command line arguments or default values
   output_file = args.output
   max_pages = args.max_pages
   delay = args.delay
   respect_robots = False if args.ignore_robots else False  # Default to False
   site_list = args.sites if args.sites else websites
   content_only = True  # Default to True
   
   # Update content_only based on command line arguments
   if args.all_pages:
       content_only = False
       
   # Update respect_robots based on command line arguments
   if args.respect_robots:
       respect_robots = True
       
   print(f"Knowledge Base Generator Configuration:")
   print(f"  - Output file: {output_file}")
   print(f"  - Max content pages per domain: {max_pages}")
   print(f"  - Request delay: {delay} seconds")
   print(f"  - Respect robots.txt: {respect_robots}")
   print(f"  - Sites to crawl: {len(site_list)}")
   print(f"  - Content-only mode: {content_only}")
   
   start_time = time.time()
   
   # Create knowledge base generator
   generator = KnowledgeBaseGenerator(
       output_file=output_file,
       max_pages_per_domain=max_pages,
       delay=delay,
       respect_robots=respect_robots,
       content_only=content_only
   )
   
   # Crawl websites
   generator.crawl_websites(site_list)
   
   # Add metadata
   generator.add_metadata()
   
   # Generate categorical view
   generator.generate_categories()
   
   end_time = time.time()
   total_time = end_time - start_time
   minutes = int(total_time // 60)
   seconds = int(total_time % 60)
   
   print(f"\nCrawling completed in {minutes} minutes and {seconds} seconds")
   print(f"Total pages crawled: {generator.stats['pages_crawled']}")
   print(f"Total pages skipped: {generator.stats['pages_skipped']}")
   print(f"Total errors: {generator.stats['errors']}")
   print(f"Knowledge base saved to: {output_file}")
   print(f"Categorical view saved to: {os.path.splitext(output_file)[0] + '_categories.json'}")


if __name__ == "__main__":
   main()

                    
