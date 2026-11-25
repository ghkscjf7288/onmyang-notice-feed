"""예약 작업 환경에서 실행하는 공개 공식 공지 중계 파일 생성기. 토큰 불필요."""
import argparse
import asyncio
import hashlib
import json
import re
import urllib.request
from dataclasses import dataclass,asdict,field
from datetime import datetime
from html.parser import HTMLParser
from pathlib import Path
from zoneinfo import ZoneInfo
from urllib.parse import unquote,urljoin,urlsplit
from bs4 import BeautifulSoup
KST=ZoneInfo('Asia/Seoul')
def patch_priority(title):
    if re.search(r'스킨|크로마|상점|보급고|제작소|치장|코스튬|상품|판매', title):
        return 3
    if re.search(r'챔피언|직업|스킬|밸런스|전투|건 플레이|게임 플레이|사냥|보스|경쟁전|매치|오류|버그|성능|입장|무릉', title):
        return 0
    if re.search(r'시스템|아이템|월드|맵|편의|UX|UI|음성', title):
        return 1
    return 2


def signed_image_url(url):
    # Nested proxy URLs may percent-encode the original signature parameters.
    decoded = url
    for _ in range(4):
        next_value = unquote(decoded)
        if next_value == decoded:
            break
        decoded = next_value
    return bool(re.search(
        r'[?&#;](?:tok|token|access_token|auth_token|signature|sig|x-amz-[\w-]+|x-goog-[\w-]+|key-pair-id|policy)=',
        decoded, re.I,
    ))


def patch_images(article, base):
    result, seen, section, major = [], set(), '관련 이미지', ''
    for node in article.find_all(['h2', 'h3', 'h4', 'img']):
        if node.name != 'img':
            section = node.get_text(' ', strip=True)
            if node.name == 'h2':
                major = section
            elif patch_priority(major) == 3:
                section = major + ' · ' + section
            continue
        source = node.get('data-src') or node.get('src', '')
        if not source or source.startswith('data:'):
            continue
        source = urljoin(base, source)
        parsed = urlsplit(source)
        dimensions = re.search(r'-(\d+)x(\d+)\.', source)
        width = str(node.get('width', ''))
        width = int(width) if width.isdigit() else int(dimensions[1]) if dimensions else None
        if (parsed.scheme != 'https' or not parsed.hostname or parsed.username or parsed.password or
                signed_image_url(source) or
                (width is not None and width <= 300) or
                re.search(r'/img/(?:champion|spell|item)/|icon|logo', source, re.I) or source in seen):
            continue
        image_section = section
        if urlsplit(base).hostname == 'mapleplanet.io':
            for parent in node.find_parents('li'):
                own = BeautifulSoup(str(parent), 'html.parser').find('li')
                for nested in own.find_all(['ul', 'ol']):
                    nested.decompose()
                context = own.get_text(' ', strip=True)
                if context:
                    image_section = patch_topic(section, context)
                    break
        seen.add(source)
        result.append((image_section, source))
    return result


def patch_topic(section, text):
    intro = text.split(' · ', 1)[0]
    for label, pattern in (
        ('월드 입장 인원', r'최대\s*입장\s*인원'),
        ('경매장', r'경매장'),
        ('무릉도장', r'무릉도장'),
        ('길드', r'길드'),
        ('패밀리', r'패밀리'),
        ('이벤트', r'버닝|이벤트|코인샵'),
    ):
        if re.search(pattern, intro):
            return label
    return '시스템' if re.search(r'최대\s*입장\s*인원', section) else section


class PartyError(ValueError): pass
WORLD='https://maplestoryworlds.nexon.com'
PLANET='https://mapleplanet.io'
LISTS={'world':WORLD+'/ko/community/5005/2120','planet':PLANET+'/news/notices','patch':PLANET+'/news/updates','event':PLANET+'/news/events'}
LABELS={'world':'월드 공지','planet':'플래닛 공지','patch':'플래닛 패치노트','event':'플래닛 이벤트'}
STRING=r'"(?:[^"\\]|\\.)*"'
TOKEN=rf'(?:{STRING}|[A-Za-z_$][\w$]*|\d+)'
class Plain(HTMLParser):
    def __init__(self):
        super().__init__(); self.parts=[]; self.hidden=0
    def handle_starttag(self,tag,attrs):
        if tag in ('script','style'): self.hidden+=1
        if not self.hidden and tag in ('p','br','li','h1','h2','h3','h4','tr'): self.parts.append('\n')
    def handle_endtag(self,tag):
        if tag in ('script','style'): self.hidden=max(0,self.hidden-1)
        if not self.hidden and tag in ('p','li','h1','h2','h3','h4','tr'): self.parts.append('\n')
    def handle_data(self,data):
        if not self.hidden: self.parts.append(data)
    def text(self):
        return '\n'.join(' '.join(line.split()) for line in ''.join(self.parts).splitlines() if line.strip())

def plain(html):
    p=Plain(); p.feed(str(html)); return p.text()

def nuxt(html):
    """Nuxt 문자열/기본값만 읽는다. 웹페이지의 JavaScript를 실행하지 않는다."""
    m=re.search(r'<script[^>]*>\s*window\.__NUXT__=(.*?)</script>',html,re.S)
    if not m: raise PartyError('월드 공지의 본문 데이터가 없습니다. 사이트 형식을 확인해야 합니다.')
    script=m[1]; params=re.match(r'\(function\(([^)]*)\)',script)
    call=script.rfind('}(')
    if not params or call<0: raise PartyError('월드 공지 데이터 형식이 변경되었습니다.')
    names=params[1].split(','); args=script[call+2:].strip().rstrip(';')
    if not args.endswith('))'): raise PartyError('월드 공지 데이터가 완전하지 않습니다.')
    args=args[:-2]; values=[]; begin=0; depth=0; quote=None; escaped=False
    for pos,char in enumerate(args):
        if quote:
            if escaped: escaped=False
            elif char=='\\': escaped=True
            elif char==quote: quote=None
        elif char in ('"',"'"): quote=char
        elif char in '([{': depth+=1
        elif char in ')]}': depth-=1
        elif char==',' and depth==0: values.append(args[begin:pos]); begin=pos+1
    values.append(args[begin:])
    if len(names)!=len(values) or len(names)>2048 or quote or depth:
        raise PartyError('월드 공지 데이터 구분에 실패했습니다.')
    env={}
    for key,value in zip(names,values):
        try: env[key]=json.loads(value)
        except ValueError: pass  # 객체 생성/대입 등 실행문은 읽지 않는다.
    def resolve(value):
        if value.startswith('"') or value.isdecimal(): return json.loads(value)
        if value in env: return env[value]
        raise PartyError('월드 공지의 필요한 값을 읽지 못했습니다.')
    return script,resolve

@dataclass
class Post:
    source:str
    key:str
    title:str
    url:str
    published:str
    body:str
    blocks:list
    images:list = field(default_factory=list)
    @property
    def digest(self):
        return hashlib.sha256(json.dumps(asdict(self),ensure_ascii=False,sort_keys=True).encode()).hexdigest()

def world_list(html):
    script,resolve=nuxt(html); result={}
    pattern=rf'threadId:({TOKEN}),headlineId:({TOKEN}),title:({TOKEN})'
    for m in re.finditer(pattern,script):
        key,title=str(resolve(m[1])),resolve(m[3])
        if key.isdecimal() and isinstance(title,str): result[key]=title
    if not result: raise PartyError('월드 공지 목록을 읽지 못했습니다.')
    return [(key,title,WORLD+f'/ko/community/5005/2120/{key}') for key,title in result.items()]

def world_post(html,key,url):
    script,resolve=nuxt(html)
    matches=list(re.finditer(r'thread:\{communityId:',script))
    for start in matches:
        part=script[start.start():]
        mid=re.search(rf'threadId:({TOKEN}),',part)
        if not mid or str(resolve(mid[1]))!=str(key): continue
        title=re.search(rf',title:({TOKEN}),summary:',part)
        body=re.search(rf',content:({TOKEN}),createDate:',part)
        created=re.search(rf',createDate:({TOKEN}),',part)
        if not all((title,body,created)): break
        raw=resolve(body[1]); name=resolve(title[1]); stamp=resolve(created[1])
        if not isinstance(raw,str) or not isinstance(name,str) or not isinstance(stamp,(int,float)): break
        text=plain(raw)
        if not text: break
        published=datetime.fromtimestamp(stamp/1000,KST).date().isoformat()
        return Post('world',str(key),name,url,published,text,[])
    raise PartyError('월드 공지의 전체 본문을 읽지 못했습니다. 잘린 소개 문구로 대신 게시하지 않습니다.')

def planet_list(html,kind):
    soup=BeautifulSoup(html,'html.parser'); result={}
    path={'patch':'updates','event':'events','planet':'notices'}[kind]
    for link in soup.find_all('a',href=True):
        href=link['href']; match=re.fullmatch(rf'/news/{path}/(\d+)',href)
        if match: result[match[1]]=(link.get_text(' ',strip=True),PLANET+href)
    if not result: raise PartyError(f'{LABELS[kind]} 목록을 읽지 못했습니다.')
    return [(key,title,url) for key,(title,url) in result.items()][:15]

def planet_post(html,kind,key,url):
    soup=BeautifulSoup(html,'html.parser'); article=soup.find('article')
    if not article or not article.find('h1'): raise PartyError('플래닛 공지 본문 형식이 변경되었습니다.')
    title=article.find('h1').get_text(' ',strip=True); stamp=article.find('time')
    published=(stamp.get('datetime') or stamp.get('dateTime') or '') if stamp else ''
    if not re.fullmatch(r'20\d\d-\d\d-\d\d',published): raise PartyError('플래닛 공지의 작성 날짜를 읽지 못했습니다.')
    header=article.find('header')
    if header: header.decompose()
    for node in article.find_all(['script','style']): node.decompose()
    blocks=[]; section='주요 변경'
    # 변경 목록이 있는 패치에서는 해설 문단이 핵심 변경을 밀어내지 않게 한다.
    tags=['h2','h3','h4','li'] if kind=='patch' and article.find('li') else ['h2','h3','h4','li','p']
    for node in article.find_all(tags):
        if node.name in ('h2','h3','h4'):
            heading=node.get_text(' ',strip=True)
            if '메이플플래닛 패치노트' not in heading:
                section=re.sub(r'^[^가-힣A-Za-z0-9]+','',heading)
            continue
        if node.find_parent('li'): continue
        text=' '.join(node.get_text(' ',strip=True).split())
        if node.name=='li' and node.find(['ul','ol']):
            own=BeautifulSoup(str(node),'html.parser')
            for nested in own.find_all(['ul','ol']): nested.decompose()
            base=own.get_text(' ',strip=True)
            details=[]
            for child in node.find_all('li'):
                if child.find(['ul','ol']): continue
                value=' '.join(child.get_text(' ',strip=True).split())
                numeric=bool(re.search(r'\d+(?:\.\d+)?\s*(?:초|분|회|%|메소|배)',value))
                condition=bool(re.search(r'없이|제외|않|우선|유지|만료|먼저|차례|함께|경우',value))
                if numeric or condition: details.append((not numeric,value))
            extras=[short(value,180) for _,value in sorted(details,key=lambda pair:pair[0])[:4]]
            text=base+(' · '+' / '.join(extras) if extras else '')
        if len(text)<12 or any(x in text for x in ('이용해 주셔서 감사합니다','안내해드립니다.')): continue
        if not any(c.isalnum() for c in text): continue
        blocks.append([section,text])
    body=plain(str(article))
    if len(body)<20: raise PartyError('플래닛 공지 본문이 비어 있습니다.')
    return Post(kind,str(key),title,url,published,body,blocks,patch_images(article,url))

def is_maintenance(title):
    return any(word in title for word in ('점검', '패치', '마이그레이션'))

def short(text,limit):
    return text if len(text)<=limit else text[:limit-1]+'…'

async def fetch(url):
    def get():
        request=urllib.request.Request(url,headers={'User-Agent':'Mozilla/5.0 (compatible; OnmyangBot/1.0; notice-reader)','Accept':'text/html,application/xhtml+xml'})
        with urllib.request.urlopen(request,timeout=35) as response:
            body=response.read(2_097_153)
        if len(body)>2_097_152:raise PartyError('공식 공지 응답 크기 제한 초과')
        return body.decode('utf-8-sig')
    return await asyncio.to_thread(get)

async def collect(source):
    html=await fetch(LISTS[source])
    records=world_list(html) if source=='world' else planet_list(html,source)
    if source=='world':records=[r for r in records if is_maintenance(r[1]) and not re.search(r'패치\s*노트', r[1])]
    if source=='planet':records=[r for r in records if is_maintenance(r[1]) and '메이플스토리 월드' not in r[1]]
    sem=asyncio.Semaphore(3)
    async def one(record):
        key,_,url=record
        async with sem:
            raw=await fetch(url)
            return world_post(raw,key,url) if source=='world' else planet_post(raw,source,key,url)
    posts=await asyncio.gather(*(one(row) for row in records[:10]))
    return {'status':'ok','checked_at':datetime.now(KST).isoformat(),'posts':[asdict(p) for p in posts]}

async def build():
    data={'schema_version':1,'generated_at':datetime.now(KST).isoformat(),'sources':{}}
    async def one(source):
        try:
            async with asyncio.timeout(150):result=await collect(source)
        except Exception as error:
            result={'status':'error','checked_at':datetime.now(KST).isoformat(),'error_type':type(error).__name__,'posts':[]}
        data['sources'][source]=result
    await asyncio.gather(*(one(s) for s in LISTS))
    return data

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--output',default='feed.json');args=parser.parse_args()
    data=asyncio.run(build());Path(args.output).write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding='utf-8')
    for name,value in data['sources'].items():print(name,value['status'],len(value['posts']))

