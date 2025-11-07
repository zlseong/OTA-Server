# PQC TLS Wrapper Library Makefile
# Compiles to shared library (.so) for Python ctypes

CC = gcc
CFLAGS = -Wall -Wextra -O2 -fPIC -I/usr/local/include
LDFLAGS = -shared -L/usr/local/lib -lssl -lcrypto

# macOS specific
UNAME := $(shell uname -s)
ifeq ($(UNAME), Darwin)
    CFLAGS += -I/opt/homebrew/include
    LDFLAGS += -L/opt/homebrew/lib
    LIB_EXT = dylib
else
    LIB_EXT = so
endif

# Target library
TARGET = libpqc_tls.$(LIB_EXT)

# Source files
SOURCES = pqc_tls_wrapper.c
OBJECTS = $(SOURCES:.c=.o)

all: $(TARGET)

$(TARGET): $(OBJECTS)
	$(CC) $(OBJECTS) -o $(TARGET) $(LDFLAGS)
	@echo "✅ PQC TLS library built: $(TARGET)"

%.o: %.c pqc_tls_wrapper.h
	$(CC) $(CFLAGS) -c $< -o $@

clean:
	rm -f $(OBJECTS) $(TARGET)
	@echo "🧹 Cleaned"

install:
	cp $(TARGET) ../server/$(TARGET)
	@echo "📦 Installed to ../server/"

.PHONY: all clean install



