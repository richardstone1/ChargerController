import uasyncio as asyncio

async def handle_client(reader, writer):
    print("client connected")
    try:
        req = await reader.read(1024)
        print("request:", req)

        body = "<html><body><h1>Pico W web server works</h1></body></html>"
        resp = (
            "HTTP/1.1 200 OK\r\n"
            "Content-Type: text/html\r\n"
            "Connection: close\r\n"
            "Content-Length: {}\r\n"
            "\r\n"
            "{}"
        ).format(len(body), body)

        await writer.awrite(resp)
    except Exception as ex:
        print("handle_client error:", ex)
    finally:
        try:
            await writer.aclose()
        except Exception as ex:
            print("writer close error:", ex)

async def web_server(ctrl, host="0.0.0.0", port=80):
    print("starting web server")
    server = await asyncio.start_server(handle_client, host, port)
    print("Web server listening on {}:{}".format(host, port))
    await server.wait_closed()