from build_cloud_site import DOCS_DIR, INDEX_PATH, main

if __name__ == "__main__":
      main()
      patch = '<style>.summary .metric:first-child{display:none}.summary{grid-template-columns:repeat(2,minmax(0,1fr))}</style>'
      INDEX_PATH.write_text(INDEX_PATH.read_text(encoding="utf-8").replace("</body>", patch + "</body>"), encoding="utf-8")
  
