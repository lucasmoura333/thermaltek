# Makefile for Nuvoton RGB Controller Kernel Module

# Module name
obj-m += nuvoton-rgb.o

# Kernel build directory
KDIR := /lib/modules/$(shell uname -r)/build

# Current directory
PWD := $(shell pwd)

# Build targets
all:
	$(MAKE) -C $(KDIR) M=$(PWD) modules

clean:
	$(MAKE) -C $(KDIR) M=$(PWD) clean

install:
	$(MAKE) -C $(KDIR) M=$(PWD) modules_install
	depmod -a

uninstall:
	rm -f /lib/modules/$(shell uname -r)/extra/nuvoton-rgb.ko
	depmod -a

load:
	insmod nuvoton-rgb.ko

unload:
	rmmod nuvoton-rgb

reload: unload load

# Help target
help:
	@echo "Nuvoton RGB Controller Driver Makefile"
	@echo ""
	@echo "Targets:"
	@echo "  all       - Build the kernel module"
	@echo "  clean     - Remove build artifacts"
	@echo "  install   - Install module to system"
	@echo "  uninstall - Remove module from system"
	@echo "  load      - Load module into kernel"
	@echo "  unload    - Unload module from kernel"
	@echo "  reload    - Unload and reload module"
	@echo ""
	@echo "Usage:"
	@echo "  make          - Build the module"
	@echo "  sudo make install - Install to system"
	@echo "  sudo make load    - Load into kernel"

.PHONY: all clean install uninstall load unload reload help
