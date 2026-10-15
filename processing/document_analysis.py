"""Static publisher-media and patent metadata extraction inside the isolated parser."""
import re


def enrich_html(soup):
    media=[]
    for tag in soup.find_all('meta'):
        if tag.get('property') in ('og:image','og:image:secure_url') or tag.get('name')=='twitter:image':
            media.append({'href':str(tag.get('content',''))[:3000],'caption':'Publisher page preview image','origin':'publisher meta tag','attribution':'PUBLISHER ASSERTED / SUBJECT UNVERIFIED'})
    for image in soup.find_all('img')[:250]:
        href=image.get('data-src') or image.get('src')
        if not href or str(href).startswith('data:'):continue
        figure=image.find_parent('figure');caption=figure.find('figcaption') if figure else None
        media.append({'href':str(href)[:3000],'caption':(caption.get_text(' ',strip=True) if caption else str(image.get('alt','')))[:1000],'origin':'image element / caption','attribution':'PUBLISHER ASSERTED / SUBJECT UNVERIFIED'})
    result={'media':media[:250]}
    if soup.find('meta',attrs={'name':'DC.type','content':'patent'}):
        def prop(name):
            el=soup.find(attrs={'itemprop':name});return (el.get('datetime') or el.get_text(' ',strip=True))[:1000] if el else None
        def meta(name,scheme=None):
            attrs={'name':name}
            if scheme:attrs['scheme']=scheme
            return [str(x.get('content','')).strip()[:4000] for x in soup.find_all('meta',attrs=attrs)][:100]
        claims=[]
        section=soup.find(attrs={'itemprop':'claims'})
        if section:
            for tag in section.find_all(['claim','div'],recursive=True):
                if tag.name=='claim' or 'claim-text' in tag.get('class',[]):
                    text=tag.get_text(' ',strip=True)
                    if text and text not in claims:claims.append(text[:8000])
            if not claims:claims=[section.get_text(' ',strip=True)[:16000]]
        linked=[];seen=set()
        for a in soup.find_all('a',href=True):
            href=str(a['href']);match=re.search(r'/patent/([A-Z]{2}\d+[A-Z]\d?)(?:/|$)',href)
            if match and href not in seen:
                seen.add(href);table=a.find_parent('table');heading=table.find_previous(['h2','h3']) if table else None
                linked.append({'identifier':match[1],'href':href,'label':a.get_text(' ',strip=True)[:300],'section_heading':heading.get_text(' ',strip=True)[:300] if heading else 'Linked patent; relationship requires review'})
        result['patent']={'publication_number':meta('citation_patent_publication_number'),'application_number':meta('citation_patent_application_number'),'title':meta('DC.title'),'pdf_urls':meta('citation_pdf_url'),'inventors':meta('DC.contributor','inventor'),'assignees':meta('DC.contributor','assignee'),'priority_date':prop('priorityDate'),'filing_date':prop('filingDate'),'publication_date':prop('publicationDate'),'displayed_legal_status':prop('legalStatusIfi'),'abstract':prop('abstract'),'claims':claims[:100],'references':meta('DC.relation','references'),'classifications':[x.get_text(' ',strip=True)[:300] for x in soup.find_all(attrs={'itemprop':'Code'})[:100]],'linked_patents':linked[:200],'source_warning':'Publisher patent disclosure and catalogue metadata, not experimental validation, current legal opinion or freedom-to-operate advice.'}
    return result
