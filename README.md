# Knowledge Base Generator

A sophisticated web crawling and content extraction tool designed to build structured knowledge bases from multiple websites. This tool intelligently identifies and prioritizes content-rich pages, extracts meaningful text with preserved structure, and organizes everything into a searchable JSON knowledge base.

## Features

- **Intelligent Content Prioritization**: Focuses on content-rich pages (articles, blogs, FAQs, guides) while skipping navigational pages
- **Structural Content Extraction**: Preserves document structure (headings, paragraphs, lists) for better knowledge representation
- **Domain-focused Crawling**: Configurable crawling limits per domain to ensure balanced knowledge collection
- **Duplicate Content Detection**: Identifies and removes duplicate content across and within pages
- **Ethical Crawling**: Built-in delay between requests and optional respect for robots.txt
- **Content Classification**: Automatic page type classification to organize knowledge by categories
- **Categorical Views**: Generates alternative JSON output with content organized by categories
- **Comprehensive Statistics**: Detailed crawling statistics and error tracking

## Installation

```bash
# Clone the repository
git clone https://github.com/yourusername/knowledge-base-generator.git
cd knowledge-base-generator

# Install requirements
pip install -r requirements.txt
```

## Usage

### Basic Usage

```bash
python knowledge_base_generator.py
```

This will crawl the default websites with the default configuration.

### Command Line Options

```bash
python knowledge_base_generator.py --output caregiving_kb.json --max-pages 30 --delay 1.5
```

### All Available Options

| Option | Short | Description | Default |
|--------|-------|-------------|---------|
| `--output` | `-o` | Output JSON file | `caregiving_knowledge_base.json` |
| `--max-pages` | `-m` | Maximum pages per domain | `50` |
| `--delay` | `-d` | Delay between requests (seconds) | `2.0` |
| `--ignore-robots` | `-i` | Ignore robots.txt | `True` |
| `--respect-robots` | `-r` | Respect robots.txt | `False` |
| `--sites` | `-s` | Specific sites to crawl | Default list |
| `--content-only` | `-c` | Crawl only content-rich pages | `True` |
| `--all-pages` | `-a` | Crawl all page types | `False` |

### Example with Custom Sites

```bash
python knowledge_base_generator.py --sites https://example.com https://anothersite.org --max-pages 20
```

## Output Structure

The tool generates two JSON files:

1. **Main Knowledge Base** (`caregiving_knowledge_base.json`): Contains the full extracted content with the following structure:
   ```json
   {
     "domain.com": {
       "base_url": "https://domain.com",
       "pages": {
         "https://domain.com/page1": {
           "type": "article",
           "content": {
             "title": "Page Title",
             "meta_description": "Description",
             "headings": { "h1": [...], "h2": [...] },
             "paragraphs": [...],
             "lists": [...]
           },
           "depth": 1,
           "crawled_at": "2023-01-01 12:00:00"
         }
       },
       "stats": {
         "pages_crawled": 20,
         "by_type": { "article": 10, "faq": 5, ... }
       }
     },
     "_metadata": { ... }
   }
   ```

2. **Categorical View** (`caregiving_knowledge_base_categories.json`): Organizes content by category for easier navigation.

## Customization

The `KnowledgeBaseGenerator` class can be customized for specific needs:

```python
generator = KnowledgeBaseGenerator(
    output_file="custom_kb.json",
    max_pages_per_domain=100,
    delay=1.0,
    respect_robots=True,
    content_only=True
)

# Custom website list
websites = [
    "https://example.com/",
    "https://anothersite.org/"
]

generator.crawl_websites(websites)
```

## Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

## License

This project is licensed under the MIT License - see the LICENSE file for details.
