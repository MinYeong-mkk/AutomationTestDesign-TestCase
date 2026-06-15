from datetime import datetime


def page_header(title: str, subtitle: str = "") -> str:
    sub = f"<p>{subtitle}</p>" if subtitle else ""
    return f"""
<h2>{title}</h2>
<p>생성일: {datetime.now().strftime('%Y-%m-%d %H:%M')}</p>
{sub}
""".strip()


def table(headers: list, rows: list) -> str:
    """headers: 컬럼명 리스트 / rows: 각 행을 리스트로"""
    ths = "".join(f"<th>{h}</th>" for h in headers)
    trs = "".join(
        "<tr>" + "".join(f"<td>{cell}</td>" for cell in row) + "</tr>"
        for row in rows
    )
    return f"<table><tr>{ths}</tr>{trs}</table>"


def section(title: str, content: str, level: int = 3) -> str:
    return f"<h{level}>{title}</h{level}>\n{content}\n"


def info_panel(text: str) -> str:
    """Confluence info 매크로"""
    return f'<ac:structured-macro ac:name="info"><ac:rich-text-body><p>{text}</p></ac:rich-text-body></ac:structured-macro>'


def code_block(code: str, language: str = "none") -> str:
    return f'<ac:structured-macro ac:name="code"><ac:parameter ac:name="language">{language}</ac:parameter><ac:plain-text-body><![CDATA[{code}]]></ac:plain-text-body></ac:structured-macro>'
