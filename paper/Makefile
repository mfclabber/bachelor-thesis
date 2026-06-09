MAIN = main
LATEXMK = latexmk
LUALATEX = lualatex

.PHONY: all clean

all:
	$(LATEXMK) -lualatex -bibtex -shell-escape $(MAIN).tex

clean:
	$(LATEXMK) -C
	rm -f *.bbl *.bcf *.run.xml
