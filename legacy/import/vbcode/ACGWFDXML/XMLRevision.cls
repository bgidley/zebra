VERSION 1.0 CLASS
BEGIN
  MultiUse = -1  'True
  Persistable = 0  'NotPersistable
  DataBindingBehavior = 0  'vbNone
  DataSourceBehavior  = 0  'vbNone
  MTSTransactionMode  = 0  'NotAnMTSObject
END
Attribute VB_Name = "XMLRevision"
Attribute VB_GlobalNameSpace = False
Attribute VB_Creatable = True
Attribute VB_PredeclaredId = False
Attribute VB_Exposed = True
'/*
' * Copyright 2004 Anite - Central Government Division
' *    http://www.anite.com/publicsector
' *
' * Licensed under the Apache License, Revision 2.0 (the "License");
' * you may not use this file except in compliance with the License.
' * You may obtain a copy of the License at
' *
' *    http://www.apache.org/licenses/LICENSE-2.0
' *
' * Unless required by applicable law or agreed to in writing, software
' * distributed under the License is distributed on an "AS IS" BASIS,
' * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
' * See the License for the specific language governing permissions and
' * limitations under the License.
' */
Option Explicit
Private Const mcstrXMLRevision As String = "1.0"

Public Function FileLoadXML(FileName As String, oRevisions As Revisions, oTaskTemplates As TaskTemplates, oProcessTemplates As ProcessTemplates) As Boolean
    On Error GoTo Err_Handler
    Dim oDoc As MSXML2.DOMDocument
    Dim oRoot As MSXML2.IXMLDOMNode
    Set oDoc = New MSXML2.DOMDocument
    oDoc.Load FileName
    
    Set oRoot = oDoc.firstChild
    
    If oRoot.nodeName <> "ACGWFDNative" Then
        FileLoadXML = False
        Exit Function
    End If
    Dim strRevision As String
    strRevision = oRoot.Attributes.getNamedItem("Revision").nodeValue
    
    Dim oNode As IXMLDOMNode
    
    If strRevision = mcstrXMLRevision Then
        FileLoadXML = XMLRevisions(oRevisions, oRoot.firstChild, oProcessTemplates, oTaskTemplates)
    Else
        '/ bad version number
        FileLoadXML = False
    End If
    Exit Function
Err_Handler:
    Stop
    Resume 0
End Function

Private Function XMLRevisions(oRevisions As Revisions, oRoot As MSXML2.IXMLDOMNode, oProcessTemplates As ProcessTemplates, oTaskTemplates As TaskTemplates) As Boolean
    On Error GoTo Err_Handler
    
    Dim oNode As IXMLDOMNode
    
    If StrComp(oRoot.nodeName, "Revisions", vbTextCompare) <> 0 Then
        Exit Function
    End If
    
    For Each oNode In oRoot.childNodes
        If StrComp(oNode.nodeName, "Revision", vbTextCompare) = 0 Then
            If Not XMLRevision(oRevisions, oNode, oProcessTemplates, oTaskTemplates) Then
                Exit Function
            End If
        End If
    Next
    XMLRevisions = True
    Exit Function
Err_Handler:
    Stop
    Resume 0
End Function
Private Function XMLRevision(oRevisions As Revisions, oRoot As MSXML2.IXMLDOMNode, oProcessTemplates As ProcessTemplates, oTaskTemplates As TaskTemplates) As Boolean
    On Error GoTo Err_Handler
    
    Dim oNode As IXMLDOMNode
    
    If StrComp(oRoot.nodeName, "Revision", vbTextCompare) <> 0 Then
        Exit Function
    End If
    
    Dim lngRevision As Long
    lngRevision = CLng(GetNodeAttr(oRoot, "RevisionID", -1))
    
    If lngRevision = -1 Then
        '/ something wrong!
        Exit Function
    End If
    
    Dim oImport As XMLProcessDef
    Dim oProcessDef As ProcessDef
    
    Set oProcessDef = New ProcessDef
    
    Set oImport = New XMLProcessDef
    
    For Each oNode In oRoot.childNodes
        If StrComp(oNode.nodeName, "ProcessDef", vbTextCompare) = 0 Then
            If Not (oImport.XMLProcess(oProcessDef, oNode, oProcessTemplates, oTaskTemplates)) Then
                Exit Function
            End If
            
        End If
    Next
    
    oRevisions.Add oProcessDef, lngRevision
    
    XMLRevision = True
    Exit Function
Err_Handler:
    Stop
    Resume 0
End Function

'/ saves the process definition to an XML file
Public Function FileSaveXML(FileName As String, oRevisions As Revisions, oProcessDef As ProcessDef) As Boolean
    
    Dim oRevision As Revision
    Set oRevision = oRevisions.Add(oProcessDef)
    
    '/ now have our version number
    
    Dim oRoot As MSXML2.IXMLDOMNode
    
    Dim oDoc As MSXML2.DOMDocument
    Set oDoc = GetDoc(FileName)
    Set oRoot = GetRevisionRoot(oDoc.firstChild)
    Dim oNode As MSXML2.IXMLDOMNode
    Set oNode = XMLNode(oRoot, "Revision")
    oRoot.appendChild oNode
    XMLAttr oNode, "RevisionID", oRevision.version
    Dim oExport As XMLProcessDef
    Set oExport = New XMLProcessDef
    
    If Not oExport.ProcessXML(oProcessDef, oNode) Then
        Exit Function
    End If
    
    oDoc.save FileName
    
    FileSaveXML = True
End Function

Private Function GetDoc(FileName As String) As DOMDocument
    Dim oDoc As DOMDocument
    Dim oRoot As IXMLDOMNode
    If Len(Dir$(FileName)) > 0 Then
        Set oDoc = New DOMDocument
        oDoc.Load FileName
        Set GetDoc = oDoc
        Exit Function
    End If
    
    Set oRoot = XMLDoc("ACGWFDNative")
    XMLAttr oRoot, "Revision", mcstrXMLRevision
        
    oRoot.appendChild XMLNode(oRoot, "Revisions")
    Set GetDoc = oRoot.ownerDocument
End Function

Private Function GetRevisionRoot(oRoot As IXMLDOMNode) As IXMLDOMNode
    Dim oNode As IXMLDOMNode
    If oRoot.nodeName <> "ACGWFDNative" Then
        Exit Function
    End If
    For Each oNode In oRoot.childNodes
        If StrComp(oNode.nodeName, "Revisions", vbTextCompare) = 0 Then
            Set GetRevisionRoot = oNode
            Exit Function
        End If
    Next
    
End Function
    

