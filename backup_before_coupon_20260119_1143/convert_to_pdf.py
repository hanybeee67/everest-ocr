import os
from markdown_pdf import MarkdownPdf, Section

def convert_md_to_pdf(input_file, output_file):
    if not os.path.exists(input_file):
        print(f"Error: {input_file} not found.")
        return

    with open(input_file, 'r', encoding='utf-8') as f:
        content = f.read()

    pdf = MarkdownPdf(toc_level=0)
    pdf.add_section(Section(content))
    
    # 폰트 문제로 한글이 깨질 수 있으므로, 기본 폰트 설정이 필요할 수 있습니다.
    # markdown-pdf 라이브러리는 기본적으로 한글 폰트를 내장하지 않을 수 있습니다.
    # 하지만 일단 실행해보고 결과를 봅니다.
    
    pdf.save(output_file)
    print(f"Successfully converted {input_file} to {output_file}")

if __name__ == "__main__":
    convert_md_to_pdf("report.md", "report.pdf")
