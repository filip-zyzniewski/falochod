SPICE=ngspice
NUTMEG=ngnutmeg
NETLIST=gnetlist

all: show

irf_spice.zip:
	wget http://www.irf.com/product-info/models/spice/spice.zip -O $@

%.spi: irf_spice.zip
	unzip -p $< $@ | tr -d '\r' > $@

%.net: %.sch
	$(NETLIST) -n -g spice-sdb -o $@ $<

power_stage.sch: irfp4668.spi

simulation.raw: power_stage.net simulation.batch
	cat $^ | $(SPICE) -r $@

.PHONY: show

show: simulation.raw
	$(NUTMEG) $^
