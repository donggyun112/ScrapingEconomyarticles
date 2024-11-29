from flask import Flask, render_template, jsonify, Response
import requests
from bs4 import BeautifulSoup
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.service import Service
import json
from flask_cors import CORS
import time
from functools import wraps
import copy
import threading

import sys
from flask import redirect, url_for, request, send_from_directory
import os
import webbrowser

from pathlib import Path
from datetime import datetime
# timedelta
from datetime import timedelta
from threading import Lock


app = Flask(__name__, static_folder='static')
CORS(app)
def open_browser():
    """브라우저를 자동으로 여는 함수"""
    # 서버가 완전히 시작될 때까지 잠시 대기
    time.sleep(1.5)
    try:
        # 시스템별 기본 브라우저 실행
        webbrowser.open('http://localhost:5001')
    except Exception as e:
        print(f"브라우저를 여는 중 오류 발생: {e}")



@app.route('/login')
def login_page():
    return render_template('login.html')

@app.route('/api/login', methods=['POST'])
def login():
    data = request.get_json()
    if not data or not data.get('email') or not data.get('password'):
        return jsonify({'error': '이메일과 비밀번호를 입력하세요'}), 400
        
    success = economist.login(
        '/opt/homebrew/bin/chromedriver',
        data.get('email'),
        data.get('password')
    )
    
    if success:
        return jsonify({'message': '로그인 성공'})
    return jsonify({'error': '로그인 실패'}), 401

def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not economist.is_logged_in:
            return jsonify({'error': 'Login required'}), 401
        return f(*args, **kwargs)
    return decorated_function

class CachedContent:
    def __init__(self, content, etag=None, last_modified=None):
        self.content = content
        self.etag = etag
        self.last_modified = last_modified
        self.timestamp = datetime.now()

class ArticleCache:
    def __init__(self, cache_duration=timedelta(hours=1)):
        self.cache = {}
        self.cache_duration = cache_duration
        self.lock = Lock()

    def get(self, url):
        """캐시된 컨텐츠 조회"""
        with self.lock:
            if url in self.cache:
                cached_data = self.cache[url]
                if datetime.now() - cached_data.timestamp < self.cache_duration:
                    return cached_data
            return None

    def set(self, url, content, etag=None, last_modified=None):
        """컨텐츠 캐시 저장"""
        with self.lock:
            self.cache[url] = CachedContent(content, etag, last_modified)

    def invalidate(self, url=None):
        """캐시 무효화"""
        with self.lock:
            if url:
                self.cache.pop(url, None)
            else:
                self.cache.clear()



class EconomistSession:
	_instance = None
	
	def __new__(cls):
		if cls._instance is None:
			cls._instance = super().__new__(cls)
		return cls._instance
	
	def __init__(self):
		if not hasattr(self, 'initialized'):
			self.session = requests.Session()
			self.headers = {
				'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
			}
			self.session.headers.update(self.headers)
			self.initialized = True
			self.is_logged_in = False
			self.driver = None
			self.article_cache = ArticleCache()
			self.latest_articles_cache = {
				'data': None,
				'timestamp': None,
				'etag': None,
				'last_modified': None
			}
			self.cache_duration = timedelta(hours=1)
    
	def _make_conditional_request(self, url, cached_data=None):
		"""조건부 요청을 수행하여 컨텐츠가 변경되었는지 확인"""
		headers = {}
		if cached_data:
			if cached_data.etag:
				headers['If-None-Match'] = cached_data.etag
				print(f"Using ETag: {cached_data.etag}")  # 디버그 로그
			if cached_data.last_modified:
				headers['If-Modified-Since'] = cached_data.last_modified
				print(f"Using Last-Modified: {cached_data.last_modified}")  # 디버그 로그

		response = self.session.get(url, headers=headers)
		print(f"Response status: {response.status_code}")  # 디버그 로그
		print(f"Response headers: {dict(response.headers)}")  # 디버그 로그

		if response.status_code == 304:  # Not Modified
			print("Content not modified, using cache")  # 디버그 로그
			return None, None, None
		
		print("Content modified or new request")  # 디버그 로그
		return (
			response.text,
			response.headers.get('ETag'),
			response.headers.get('Last-Modified')
		)


			
	def translate_text(self, text, target_lang='ko'):
		"""Google Translate API를 사용하여 텍스트를 번역합니다."""
		if not text.strip():
			return ''
			
		try:
			url = 'https://translate.googleapis.com/translate_a/single'
			params = {
				'client': 'gtx',
				'sl': 'auto',
				'tl': target_lang,
				'dt': 't',
				'q': text
			}
			
			response = requests.get(url, params=params)
			
			if response.status_code == 200:
				try:
					result = response.json()
					translated_text = ''
					for sentence in result[0]:
						if sentence[0]:
							translated_text += sentence[0]
					return translated_text
				except Exception as e:
					print(f"Translation parsing error: {e}")
					return text
			else:
				return text
				
		except Exception as e:
			print(f"Translation error: {e}")
			return text

	def process_article_content(self, article_content, base_url):
		# 불필요한 요소 제거
		for element in article_content.find_all(['div', 'aside'], class_=['css-10pit5x', 'advert', 'newsletter-form']):
			element.decompose()
			
		# 이미지 URL 수정
		for img in article_content.find_all('img'):
			if img.get('src') and not img['src'].startswith('http'):
				img['src'] = f"{base_url}/{img['src'].lstrip('/')}"
		
		# 번역할 요소들 처리
		processed_content = []
		for element in article_content.find_all(['p', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6']):
			if element.string and element.string.strip():
				original_text = element.string.strip()
				translated_text = self.translate_text(original_text)
				
				processed_content.append({
					'tag': element.name,
					'original': original_text,
					'translated': translated_text,
					'classes': element.get('class', [])
				})

		return processed_content

	def login(self, driver_path, username, password):
		if self.driver and self.is_logged_in:
			return True
			
		try:
			service = Service(driver_path)
			options = webdriver.ChromeOptions()
			options.add_argument('--disable-blink-features=AutomationControlled')
			# Headless 모드 설정
			options.add_argument('--headless')  # 브라우저 창을 표시하지 않음
			options.add_argument('--disable-gpu')  # Windows에서 필요한 옵션
			options.add_argument('--window-size=1920,1080')  # 창 크기 설정
			
			self.driver = webdriver.Chrome(service=service, options=options)
			
			self.driver.get('https://www.economist.com/api/auth/login')
			time.sleep(2)
			
			id_input = WebDriverWait(self.driver, 10).until(
				EC.presence_of_element_located((By.XPATH, '//*[@id="input-6"]'))
			)
			id_input.send_keys(username)
			
			password_input = self.driver.find_element(By.XPATH, '//*[@id="input-8"]')
			password_input.send_keys(password)
			
			login_button = self.driver.find_element(By.XPATH, '//button[contains(text(), "Log in")]')
			login_button.click()
			
			time.sleep(5)
			cookies = self.driver.get_cookies()
			
			for cookie in cookies:
				self.session.cookies.set(cookie['name'], cookie['value'])
			
			self.is_logged_in = True
			return True
				
		except Exception as e:
			print(f"Login failed: {e}")
			if self.driver:
				self.driver.quit()
				self.driver = None
			return False
			
		finally:
			if self.driver:
				self.driver.quit()
				self.driver = None

	def get_latest_articles(self):
		if not self.is_logged_in:
			return None

		url = "https://www.economist.com/latest-updates"
		
		try:
			# 캐시된 데이터 확인
			cached_data = self.article_cache.get(url)
			
			# 조건부 요청 수행
			content, etag, last_modified = self._make_conditional_request(
				url, 
				cached_data
			)
			
			# 컨텐츠가 변경되지 않았다면 캐시된 데이터 반환
			if content is None and cached_data:
				return json.loads(cached_data.content)
			
			# 새로운 컨텐츠 파싱
			start_marker = '{"@context":"https://schema.org","@type":"itemList"'
			end_marker = '</script>'
			json_start = content.find(start_marker)
			json_end = content.find(end_marker, json_start)

			json_data = content[json_start:json_end].strip()
			data = json.loads(json_data)

			articles = []
			for item in data['itemListElement'][:3]:
				article = {
					'title': item['item']['headline'],
					'url': item['item']['url'],
					'date': item['item']['datePublished']
				}
				articles.append(article)

			# 캐시 업데이트
			self.article_cache.set(
				url,
				json.dumps(articles),
				etag,
				last_modified
			)
			
			return articles
			
		except Exception as e:
			print(f"Failed to get articles: {str(e)}")
			# 에러 발생 시 캐시된 데이터 반환 (있는 경우)
			if cached_data:
				return json.loads(cached_data.content)
			return None


	def get_article(self, url):
		if not self.is_logged_in:
			return None

		try:
			# 캐시된 데이터 확인
			cached_data = self.article_cache.get(url)
			
			# 조건부 요청 수행
			content, etag, last_modified = self._make_conditional_request(
				url, 
				cached_data
			)
			
			# 컨텐츠가 변경되지 않았다면 캐시된 데이터 반환
			if content is None and cached_data:
				return cached_data.content
			
			# 새로운 컨텐츠 캐시
			if content:
				self.article_cache.set(url, content, etag, last_modified)
				return content
			
			# 에러 상황에서는 캐시된 데이터 반환 (있는 경우)
			if cached_data:
				return cached_data.content
				
			return None
			
		except Exception as e:
			print(f"Failed to get article: {str(e)}")
			# 에러 발생 시 캐시된 데이터 반환 (있는 경우)
			if cached_data:
				return cached_data.content
			return None
	
	def invalidate_cache(self, url=None):
		"""캐시를 무효화합니다."""
		if url:
			self.article_cache.invalidate(url)
		else:
			self.article_cache.invalidate()


	def modify_html(self, html_content, base_url):
		soup = BeautifulSoup(html_content, 'html.parser')
		
		new_html = BeautifulSoup('''
			<!DOCTYPE html>
			<html>
			<head>
				<meta charset="utf-8">
				<meta name="viewport" content="width=device-width, initial-scale=1">
				<title>The Economist Article</title>
				<script src="https://cdnjs.cloudflare.com/ajax/libs/react/17.0.2/umd/react.production.min.js"></script>
				<script src="https://cdnjs.cloudflare.com/ajax/libs/react-dom/17.0.2/umd/react-dom.production.min.js"></script>
				<style>
					/* 기존 스타일 유지 */
					:root {
						--ds-type-system-serif: "EconomistSerifOsF",ui-serif,Georgia,Times,"Times New Roman",serif;
						--ds-color-london-5: #0d0d0d;
						--ds-type-scale-1: 1.25rem;
						--ds-type-leading-lower: 1.4;
					}
					
					body {
						margin: 0;
						padding: 0;
						font-family: var(--ds-type-system-serif);
						background-color: #f5f5f5;
						height: 100vh;
						overflow: hidden;
					}
					.container {
						display: flex;
						flex-direction: row;  
						height: 100vh;
						margin: 0;
						padding: 0;
						width: 100%;
						background-color: white;
					}
					.article-section {
						flex: 1;
						padding: 20px;
						overflow-y: auto;
						height: 100vh;
					}
					article {
						max-width: none;
						width: 100%;
						padding: 0;
					}
					.original-section {
						border-right: 1px solid #ccc; 
					}
					.translated-section {
						background-color: #f9f9f9;
					}
					
					p {
						color: var(--ds-color-london-5);
						font-family: var(--ds-type-system-serif);
						font-size: var(--ds-type-scale-1);
						line-height: var(--ds-type-leading-lower);
						margin-bottom: 24px;
						font-weight: 500;
					}
					img {
						width: 100%; 
						height: auto;
						display: block;
						margin: 30px 0;
					}
					figure {
						margin: 30px 0;
						width: 100%;
					}
					h1 {
						font-size: 36px;
						line-height: 1.2;
						margin-bottom: 32px;
						color: var(--ds-color-london-5);
						font-weight: 500;
					}
					h2 {
						font-size: 28px;
						line-height: 1.3; 
						margin: 40px 0 24px;
						color: var(--ds-color-london-5);
					}
					h3, h4, h5, h6 {
						color: var(--ds-color-london-5);
						margin: 32px 0 16px;
					}
					figcaption {
						font-size: 14px;
						color: #666;
						margin-top: 8px;
						text-align: center;
					}
					
					@media (max-width: 1024px) {
						.container {
							flex-direction: column;
						}
						.article-section {
							height: 50vh;
							padding: 16px;
						}
						.original-section {
							border-right: none;
							border-bottom: 1px solid #ccc;
						}
					}

					.article-section::-webkit-scrollbar {
						width: 16px;
					}
					.article-section::-webkit-scrollbar-track {
						background: #f1f1f1;
					}
					.article-section::-webkit-scrollbar-thumb {
						background: #888;
						border-radius: 4px;
					}
				</style>
			</head>
			<body>
				<div id="dictionary-root"></div>
				<div class="container">
					<div class="article-section original-section" id="original-content"></div>
					<div class="article-section translated-section" id="translated-content"></div>
				</div>
				<script>
					const DictionaryPopup = () => {
						const [selection, setSelection] = React.useState({ word: '', x: 0, y: 0 });
						const [showPopover, setShowPopover] = React.useState(false);
						const [definition, setDefinition] = React.useState(null);
						const [loading, setLoading] = React.useState(false);
						const [savedWords, setSavedWords] = React.useState([]);
						const popoverRef = React.useRef(null);

						React.useEffect(() => {
							fetchSavedWords();
						}, []);

						const fetchSavedWords = async () => {
							try {
								const response = await fetch('/api/dictionary');
								if (response.ok) {
									const data = await response.json();
									setSavedWords(data);
								}
							} catch (error) {
								console.error('Error fetching saved words:', error);
							}
						};

						React.useEffect(() => {
							const handleSelection = () => {
								const selected = window.getSelection().toString().trim();
								if (selected && selected.match(/^[a-zA-Z\s$']+$/)) {
									const range = window.getSelection().getRangeAt(0);
									const rect = range.getBoundingClientRect();
									setSelection({
										word: selected,
										x: rect.left + window.scrollX,
										y: rect.bottom + window.scrollY
									});
									lookupWord(selected);
									setShowPopover(true);
								}
							};

							const originalSection = document.querySelector('.original-section');
							if (originalSection) {
								originalSection.addEventListener('mouseup', handleSelection);
								return () => originalSection.removeEventListener('mouseup', handleSelection);
							}
						}, []);

						const lookupWord = async (word) => {
							setLoading(true);
							try {
								const response = await fetch(`https://translate.googleapis.com/translate_a/single?client=gtx&sl=en&tl=ko&dt=t&q=${encodeURIComponent(word)}`);
								const data = await response.json();
								if (data[0]) {
									setDefinition({
										meaning: data[0][0][0],
										partOfSpeech: ''
									});
								}
							} catch (error) {
								setDefinition({ error: '번역을 찾을 수 없습니다' });
							}
							setLoading(false);
						};

						const saveWord = async () => {
							try {
								const response = await fetch('/api/dictionary', {
									method: 'POST',
									headers: {
										'Content-Type': 'application/json',
									},
									body: JSON.stringify({
										word: selection.word,
										definition: definition.meaning,
									}),
								});

								if (response.ok) {
									const newWord = await response.json();
									setSavedWords(prev => [newWord, ...prev]);
									setShowPopover(false);
								} else {
									console.error('Failed to save word');
								}
							} catch (error) {
								console.error('Error saving word:', error);
							}
						};

						return React.createElement('div', null,
							showPopover && React.createElement('div', {
								ref: popoverRef,
								style: {
									position: 'fixed',
									left: `${selection.x}px`,
									top: `${selection.y + 10}px`,
									backgroundColor: 'white',
									padding: '1rem',
									borderRadius: '0.5rem',
									boxShadow: '0 2px 4px rgba(0,0,0,0.1)',
									zIndex: 1000,
									maxWidth: '20rem'
								}
							},
								React.createElement('div', {
									style: {
										display: 'flex',
										justifyContent: 'space-between',
										alignItems: 'center',
										marginBottom: '0.5rem'
									}
								},
									React.createElement('h3', {
										style: {
											margin: 0,
											fontSize: '1.25rem',
											fontWeight: 'bold'
										}
									}, selection.word),
									React.createElement('div', {
										style: {
											display: 'flex',
											gap: '0.5rem'
										}
									},
										React.createElement('button', {
											onClick: saveWord,
											style: {
												border: 'none',
												background: 'none',
												cursor: 'pointer',
												color: '#3B82F6'
											}
										}, '저장'),
										React.createElement('button', {
											onClick: () => setShowPopover(false),
											style: {
												border: 'none',
												background: 'none',
												cursor: 'pointer',
												color: '#6B7280'
											}
										}, '닫기')
									)
								),
								React.createElement('div', null,
									loading ? 
										React.createElement('div', null, '로딩 중...') :
										definition ? 
											React.createElement(React.Fragment, null,
												definition.phonetic && React.createElement('div', {
													style: {
														color: '#6B7280',
														fontSize: '0.875rem'
													}
												}, definition.phonetic),
												definition.partOfSpeech && React.createElement('div', {
													style: {
														color: '#6B7280',
														fontStyle: 'italic'
													}
												}, definition.partOfSpeech),
												React.createElement('div', {
													style: {
														color: '#1F2937'
													}
												}, definition.meaning)
											) :
											React.createElement('div', {
												style: {
													color: '#EF4444'
												}
											}, '정의를 찾을 수 없습니다')
								)
							),
							React.createElement('div', {
								style: {
									position: 'fixed',
									bottom: '10rem',
									right: '1rem',
									backgroundColor: 'white',
									padding: '1rem',
									borderRadius: '0.5rem',
									boxShadow: '0 2px 4px rgba(0,0,0,0.1)',
									maxWidth: '20rem'
								}
							},
								React.createElement('h4', {
									style: {
										margin: '0 0 0.5rem 0',
										fontWeight: 'bold'
									}
								}, '저장된 단어'),
								React.createElement('div', {
									style: {
										maxHeight: '12rem',
										overflowY: 'auto'
									}
								},
									savedWords.length === 0 ?
										React.createElement('div', {
											style: {
												color: '#6B7280'
											}
										}, '저장된 단어가 없습니다') :
										React.createElement('ul', {
											style: {
												margin: 0,
												padding: 0,
												listStyle: 'none',
												display: 'flex',
												flexDirection: 'column',
												gap: '0.5rem'
											}
										},
											savedWords.map((item, index) =>
												React.createElement('li', {
													key: index,
													style: {
														fontSize: '0.875rem'
													}
												},
													React.createElement('span', {
														style: {
															fontWeight: '500'
														}
													}, item.word),
													React.createElement('p', {
														style: {
															margin: '0.25rem 0 0 0',
															color: '#6B7280'
														}
													}, item.definition)
												)
											)
										)
								)
							)
						);
					};

					let scrolling = false;
					
					function syncScroll(source, target) {
						if (!scrolling) {
							scrolling = true;
							const percentage = source.scrollTop / (source.scrollHeight - source.clientHeight);
							target.scrollTop = percentage * (target.scrollHeight - target.clientHeight);
							setTimeout(() => {
								scrolling = false;
							}, 50);
						}
					}
					
					document.addEventListener('DOMContentLoaded', () => {
						ReactDOM.render(
							React.createElement(DictionaryPopup),
							document.getElementById('dictionary-root')
						);

						const originalContent = document.getElementById('original-content');
						const translatedContent = document.getElementById('translated-content');
						
						originalContent.addEventListener('scroll', () => {
							syncScroll(originalContent, translatedContent);
						});
						
						translatedContent.addEventListener('scroll', () => {
							syncScroll(translatedContent, originalContent);
						});
					});
				</script>
			</body>
			</html>
		''', 'html.parser')

		# 원본 스타일 복사
		for css in soup.find_all('link', rel='stylesheet'):
			if css.get('href'):
				if not css['href'].startswith('http'):
					css['href'] = f"{base_url}/{css['href'].lstrip('/')}"
				new_html.head.append(css)
		
		for style in soup.find_all('style'):
			new_html.head.append(style)
				
		article_content = soup.find('article')
		if article_content:
			# 불필요한 요소들 제거
			for element in article_content.find_all(['div', 'aside'], class_=['css-10pit5x', 'advert', 'newsletter-form']):
				element.decompose()
			
			# 이미지 URL 수정 
			for img in article_content.find_all('img'):
				if img.get('src') and not img['src'].startswith('http'):
					img['src'] = f"{base_url}/{img['src'].lstrip('/')}"
            
			for a in article_content.find_all('a'):
				a.replace_with(a.get_text())
			
			# 번역용 복사본 생성
			translated_article = copy.deepcopy(article_content)
			
			# 번역이 필요한 텍스트 요소들 찾기
			for element in translated_article.find_all(['p', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'figcaption']):
				text = element.get_text().strip()
				if text:
					translated_text = self.translate_text(text)
					element.clear()
					element.append(translated_text)
			
			# 각 컬럼에 내용 추가
			original_column = new_html.find(id='original-content')
			translated_column = new_html.find(id='translated-content')
			
			original_column.append(article_content)
			translated_column.append(translated_article)

		
		return str(new_html)
		
		
	def print_original_styles(self, html_content):
		soup = BeautifulSoup(html_content, 'html.parser')
		
		# 외부 스타일시트
		for css in soup.find_all('link', rel='stylesheet'):
			if css.get('href'):
				print(f"External CSS: {css['href']}")
		
		# 내부 스타일
		for style in soup.find_all('style'):
			print("Internal CSS:", file=sys.stderr)
			print(style.string, file=sys.stderr)
		
		# 인라인 스타일
		for element in soup.find_all(style=True):
			print(f"Inline style for {element.name}: {element['style']}", file=sys.stderr)


economist = EconomistSession()

@app.route('/')
def index():
    if not economist.is_logged_in:
        return redirect(url_for('login_page'))
    return render_template('index.html')

@app.route('/api/articles', methods=['GET'])
@login_required
def get_articles():
    force_refresh = request.args.get('refresh', '').lower() == 'true'
    if force_refresh:
        economist.invalidate_cache("https://www.economist.com/latest-updates")
    
    articles = economist.get_latest_articles()
    if articles:
        return jsonify(articles)
    return jsonify({'error': 'Failed to fetch articles'}), 500

@app.route('/proxy/<path:article_url>')
@login_required
def proxy_article(article_url):
    # 브라우저 강제 새로고침 감지
    force_refresh = (
        request.args.get('refresh', '').lower() == 'true' or  # 명시적 refresh 파라미터
        request.headers.get('Cache-Control') == 'no-cache'    # 브라우저 강제 새로고침
    )
    
    full_url = f"https://www.economist.com/{article_url}"
    
    if force_refresh:
        economist.invalidate_cache(full_url)
    
    cache_key = f"{full_url}_modified"
    cached_content = economist.article_cache.get(cache_key)
    
    if cached_content and not force_refresh:
        return Response(cached_content.content, content_type='text/html')
    
    content = economist.get_article(full_url)
    
    if content:
        modified_content = economist.modify_html(content, 'https://www.economist.com')
        economist.article_cache.set(cache_key, modified_content)
        return Response(modified_content, content_type='text/html')
    return "Failed to fetch article", 500

import os
from pathlib import Path
from datetime import datetime

# 북마크 저장 디렉토리 설정
BASE_DIR = Path(__file__).resolve().parent
BOOKMARKS_DIR = BASE_DIR / 'bookmarks'
BOOKMARKS_DIR.mkdir(exist_ok=True)

@app.route('/api/bookmarks', methods=['POST'])
@login_required
def add_bookmark():
    article_url = request.json.get('url')
    if not article_url:
        return jsonify({'error': '기사 URL이 필요합니다'}), 400
        
    # URL에서 고유한 파일명 생성
    filename = datetime.now().strftime('%Y%m%d_%H%M%S') + '_' + \
              article_url.replace('https://www.economist.com/', '').replace('/', '_') + '.html'
    filepath = BOOKMARKS_DIR / filename
    
    try:
        # 기사 내용 가져오기
        article_path = article_url.replace('https://www.economist.com/', '')
        content = economist.get_article(article_url)
        if not content:
            return jsonify({'error': '기사를 가져올 수 없습니다'}), 500
            
        # HTML 수정 및 저장
        modified_content = economist.modify_html(content, 'https://www.economist.com')
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(modified_content)
        
        return jsonify({
            'id': filename,
            'url': article_url,
            'title': request.json.get('title'),
            'date': request.json.get('date'),
            'saved_path': f'/bookmarks/{filename}'
        })
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/bookmarks', methods=['GET'])
@login_required
def get_bookmarks():
    bookmarks = []
    try:
        for file in sorted(BOOKMARKS_DIR.glob('*.html'), reverse=True):
            # URL 복원 (파일명에서 날짜 부분 제거)
            file_parts = file.stem.split('_', 2)  # 날짜_시간_URL 형식으로 분리
            if len(file_parts) >= 3:
                url = 'https://www.economist.com/' + file_parts[2].replace('_', '/')
            else:
                continue  # 잘못된 파일명 형식은 건너뜀
                
            # HTML 파일에서 제목 추출
            with open(file, 'r', encoding='utf-8') as f:
                content = f.read()
                soup = BeautifulSoup(content, 'html.parser')
                title = soup.find('h1')
                title = title.text if title else file.stem
            
            bookmarks.append({
                'id': file.name,
                'url': url,
                'title': title,
                'date': datetime.strptime(file_parts[0] + file_parts[1], '%Y%m%d%H%M%S').isoformat(),
                'saved_path': f'/bookmarks/{file.name}'
            })
            
        return jsonify(bookmarks)
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/bookmarks/<path:filename>')
@login_required
def serve_bookmark(filename):
    try:
        return send_from_directory(BOOKMARKS_DIR, filename)
    except Exception as e:
        return str(e), 404

@app.route('/api/bookmarks/<filename>', methods=['DELETE'])
@login_required
def remove_bookmark(filename):
    filepath = BOOKMARKS_DIR / filename
    if not filepath.exists():
        return jsonify({'error': '북마크를 찾을 수 없습니다'}), 404
        
    try:
        filepath.unlink()  # 파일 삭제
        return jsonify({'message': '북마크가 삭제되었습니다'})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

BASE_DIR = Path(__file__).resolve().parent
DICTIONARY_DIR = BASE_DIR / 'dictionary'
DICTIONARY_DIR.mkdir(exist_ok=True)
DICTIONARY_FILE = DICTIONARY_DIR / 'words.json'

# 단어장 관련 라우트 추가
@app.route('/api/dictionary', methods=['GET'])
@login_required
def get_words():
    try:
        if DICTIONARY_FILE.exists():
            with open(DICTIONARY_FILE, 'r', encoding='utf-8') as f:
                words = json.load(f)
            return jsonify(words)
        return jsonify([])
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/dictionary', methods=['POST'])
@login_required
def save_word():
    try:
        word_data = request.json
        if not word_data or 'word' not in word_data:
            return jsonify({'error': '단어 정보가 필요합니다'}), 400

        # 현재 저장된 단어들 불러오기
        words = []
        if DICTIONARY_FILE.exists():
            with open(DICTIONARY_FILE, 'r', encoding='utf-8') as f:
                words = json.load(f)

        # 새 단어 정보 추가
        new_word = {
            'id': str(len(words) + 1),
            'word': word_data['word'],
            'definition': word_data.get('definition', ''),
            'timestamp': datetime.now().isoformat()
        }
        words.insert(0, new_word)  # 새 단어를 배열 맨 앞에 추가

        # 파일에 저장
        with open(DICTIONARY_FILE, 'w', encoding='utf-8') as f:
            json.dump(words, f, ensure_ascii=False, indent=2)

        return jsonify(new_word)

    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/dictionary/<word_id>', methods=['DELETE'])
@login_required
def delete_word(word_id):
    try:
        if not DICTIONARY_FILE.exists():
            return jsonify({'error': '단어장이 없습니다'}), 404

        with open(DICTIONARY_FILE, 'r', encoding='utf-8') as f:
            words = json.load(f)

        # 해당 ID의 단어 찾기
        words = [w for w in words if w['id'] != word_id]

        # 변경된 내용 저장
        with open(DICTIONARY_FILE, 'w', encoding='utf-8') as f:
            json.dump(words, f, ensure_ascii=False, indent=2)

        return jsonify({'message': '단어가 삭제되었습니다'})

    except Exception as e:
        return jsonify({'error': str(e)}), 500
	




if __name__ == '__main__':
	threading.Thread(target=open_browser, daemon=True).start()
      
	app.run(debug=True, port=5001)