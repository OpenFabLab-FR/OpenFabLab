"""Bounded, isolated structural PDF validation. This is not an antivirus."""
import json
from pathlib import Path
import sys

MAX_BYTES=16*1024*1024
MAX_PAGES=200
FORBIDDEN_KEYS={'/JS','/JavaScript','/OpenAction','/AA','/EmbeddedFiles','/EmbeddedFile',
    '/AcroForm','/XFA','/EF','/RichMedia','/RichMediaContent','/3D','/3DD','/Collection'}
FORBIDDEN_TYPES={'/JavaScript','/Launch','/SubmitForm','/ImportData','/GoToR','/GoToE',
                 '/Rendition','/Sound','/Movie','/Screen','/FileAttachment','/EmbeddedFile','/RichMedia','/3D'}


def inspect_pdf(path):
    import resource
    resource.setrlimit(resource.RLIMIT_CPU,(10,10))
    resource.setrlimit(resource.RLIMIT_FSIZE,(MAX_BYTES*4,MAX_BYTES*4))
    # Darwin rejects RLIMIT_DATA (even though getrlimit reports infinity) on
    # this supported development platform. Its parent enforces an RSS watchdog;
    # Linux/DSM additionally has hard kernel address/data limits in this child.
    if sys.platform.startswith('linux'):
        resource.setrlimit(resource.RLIMIT_DATA,(512*1024**2,512*1024**2))
        resource.setrlimit(resource.RLIMIT_AS,(768*1024**2,768*1024**2))
    def deny(event,args):
        if event in ('socket.connect','socket.getaddrinfo','socket.sendto','subprocess.Popen','os.system'):
            raise OSError('PDF_SANDBOX_OPERATION_REFUSED')
    sys.addaudithook(deny)
    from pypdf import PdfReader
    from pypdf.generic import DictionaryObject,ArrayObject,IndirectObject,StreamObject
    path=Path(path)
    if path.is_symlink() or not 8<=path.stat().st_size<=MAX_BYTES:
        raise ValueError('PDF_SIZE_INVALID')
    with path.open('rb') as stream:
        if stream.read(5)!=b'%PDF-':raise ValueError('PDF_TYPE_INVALID')
        stream.seek(0);reader=PdfReader(stream,strict=True)
        if reader.is_encrypted:raise ValueError('PDF_ENCRYPTED_NOT_SUPPORTED')
        if not 1<=len(reader.pages)<=MAX_PAGES:raise ValueError('PDF_PAGE_LIMIT')
        seen=set();objects=0;decompressed=0
        def visit(value,depth=0):
            nonlocal objects,decompressed
            if depth>80:raise ValueError('PDF_STRUCTURE_LIMIT')
            if isinstance(value,IndirectObject):
                key=(value.idnum,value.generation)
                if key in seen:return
                seen.add(key);value=value.get_object()
            objects+=1
            if objects>100000:raise ValueError('PDF_OBJECT_LIMIT')
            if isinstance(value,DictionaryObject):
                if FORBIDDEN_KEYS.intersection(value.keys()):raise ValueError('PDF_ACTIVE_CONTENT_REFUSED')
                if any(str(value.get(k,'')) in FORBIDDEN_TYPES for k in ('/S','/Subtype','/Type')):
                    raise ValueError('PDF_ACTIVE_CONTENT_REFUSED')
                if '/URI' in value:
                    from urllib.parse import urlsplit
                    target=str(value['/URI']);parsed=urlsplit(target)
                    if parsed.scheme not in ('https','http') or parsed.username or parsed.password or any(ord(c)<32 for c in target):
                        raise ValueError('PDF_UNSAFE_LINK_REFUSED')
                if isinstance(value,StreamObject):
                    if '/F' in value:raise ValueError('PDF_EXTERNAL_STREAM_REFUSED')
                    decompressed+=len(value.get_data())
                    if decompressed>128*1024**2:raise ValueError('PDF_DECOMPRESSION_LIMIT')
                for child in value.values():visit(child,depth+1)
            elif isinstance(value,ArrayObject):
                for child in value:visit(child,depth+1)
        visit(reader.trailer)
        for generation,entries in reader.xref.items():
            for number in entries:
                if number:visit(IndirectObject(number,generation,reader))
        for number in reader.xref_objStm:
            visit(IndirectObject(number,0,reader))
        return dict(valid=True,pages=len(reader.pages),size=path.stat().st_size)


if __name__=='__main__':
    try:
        if len(sys.argv)!=2:raise ValueError('PDF_ARGUMENT_INVALID')
        value=inspect_pdf(sys.argv[1])
    except Exception as error:
        # Deliberately no input filename, metadata, extracted text or traceback.
        import re
        reason=str(error)
        value=dict(valid=False,code=reason if re.fullmatch(r'PDF_[A-Z_]{1,70}',reason) else type(error).__name__)
    print(json.dumps(value));sys.exit(0 if value['valid'] else 1)
