import os
import time
import argparse
from datetime import datetime

# 이 스크립트는 로컬 프로젝트에서 특정 기간 내에 수정된 주요 코드만 
# 하나의 텍스트 파일로 병합하여 Gemini에게 전달하기 쉽게 해줍니다.

def export_code_to_txt(days=1.0, output_filename="code_context_for_gemini.txt"):
    # 무시할 디렉토리 및 파일 확장자 (가상환경, 캐시, 깃 등)
    ignore_dirs = {'.venv', 'venv', '.git', '__pycache__', 'node_modules', '.pytest_cache'}
    allowed_extensions = {'.py', '.md', '.json', '.env.example', '.txt', '.yaml'}

    # 기준 시간 계산 (현재 시간 - N일)
    cutoff_time = time.time() - (days * 24 * 3600)
    cutoff_date_str = datetime.fromtimestamp(cutoff_time).strftime('%Y-%m-%d %H:%M:%S')

    print(f"🔍 최근 {days}일(기준: {cutoff_date_str} 이후) 동안 수정된 파일을 검색합니다...")

    exported_count = 0
    with open(output_filename, 'w', encoding='utf-8') as outfile:
        outfile.write(f"# 프로젝트 수정 코드 컨텍스트 (최근 {days}일 이내)\n\n")
        
        for root, dirs, files in os.walk('.'):
            # 무시할 디렉토리 제외
            dirs[:] = [d for d in dirs if d not in ignore_dirs]
            
            for file in files:
                if any(file.endswith(ext) for ext in allowed_extensions) and file != output_filename:
                    file_path = os.path.join(root, file)
                    mtime = os.path.getmtime(file_path)
                    
                    # 수정일이 기준 시간 이후인 파일만 추출
                    if mtime >= cutoff_time:
                        mod_time_str = datetime.fromtimestamp(mtime).strftime('%Y-%m-%d %H:%M:%S')
                        outfile.write(f"--- 파일: {file_path} (수정일: {mod_time_str}) ---\n")
                        outfile.write("```" + file_path.split('.')[-1] + "\n")
                        
                        try:
                            with open(file_path, 'r', encoding='utf-8') as infile:
                                outfile.write(infile.read())
                            exported_count += 1
                        except Exception as e:
                            outfile.write(f"// 파일을 읽을 수 없습니다: {e}\n")
                        
                        outfile.write("\n```\n\n")
    
    if exported_count > 0:
        print(f"✅ 총 {exported_count}개의 파일이 성공적으로 '{output_filename}'에 병합되었습니다.")
        print("이 파일을 Gemini 채팅창에 업로드해주세요!")
    else:
        print("⚠️ 지정된 기간 내에 수정된 파일이 없습니다.")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="특정 기간 내 수정된 프로젝트 코드를 추출합니다.")
    parser.add_argument("-d", "--days", type=float, default=1.0, help="최근 N일 이내 수정된 파일 추출 (기본값: 1.0일)")
    parser.add_argument("-o", "--output", type=str, default="code_context_for_gemini.txt", help="출력 파일명")
    args = parser.parse_args()

    export_code_to_txt(days=args.days, output_filename=args.output)