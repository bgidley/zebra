VERSION 1.0 CLASS
BEGIN
  MultiUse = -1  'True
  Persistable = 0  'NotPersistable
  DataBindingBehavior = 0  'vbNone
  DataSourceBehavior  = 0  'vbNone
  MTSTransactionMode  = 0  'NotAnMTSObject
END
Attribute VB_Name = "XMLProcessVersion"
Attribute VB_GlobalNameSpace = False
Attribute VB_Creatable = True
Attribute VB_PredeclaredId = False
Attribute VB_Exposed = True
'/*
' * Copyright 2004 Anite - Central Government Division
' *    http://www.anite.com/publicsector
' *
' * Licensed under the Apache License, Version 2.0 (the "License");
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
Private Const mcstrXMLVersion As String = "3.0"

Public Function FileLoadXML(FileName As String, oVersions As Versions, oTaskTemplates As TaskTemplates, oProcessTemplates As ProcessTemplates) As Boolean
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
    Dim strVersion As String
    strVersion = oRoot.Attributes.getNamedItem("Version").nodeValue
    
    Dim oNode As IXMLDOMNode
    
    If strVersion = mcstrXMLVersion Then
        FileLoadXML = XMLProcessVersions(oVersions, oRoot.firstChild, oProcessTemplates, oTaskTemplates)
    Else
        '/ bad version number
        FileLoadXML = False
    End If
    Exit Function
Err_Handler:
    Stop
    Resume 0
End Function

Private Function XMLProcessVersions(oVersions As Versions, oRoot As MSXML2.IXMLDOMNode, oProcessTemplates As ProcessTemplates, oTaskTemplates As TaskTemplates) As Boolean
    On Error GoTo Err_Handler
    
    Dim oNode As IXMLDOMNode
    
    If StrComp(oRoot.nodeName, "ProcessVersions", vbTextCompare) <> 0 Then
        Exit Function
    End If
    
    For Each oNode In oRoot.childNodes
        If StrComp(oNode.nodeName, "ProcessVersion", vbTextCompare) = 0 Then
            If Not XMLVersion(oVersions, oNode, oProcessTemplates, oTaskTemplates) Then
                Exit Function
            End If
        End If
    Next
    XMLProcessVersions = True
    Exit Function
Err_Handler:
    Stop
    Resume 0
End Function
Private Function XMLVersion(oVersions As Versions, oRoot As MSXML2.IXMLDOMNode, oProcessTemplates As ProcessTemplates, oTaskTemplates As TaskTemplates) As Boolean
    On Error GoTo Err_Handler
    
    Dim oNode As IXMLDOMNode
    
    If StrComp(oRoot.nodeName, "ProcessVersion", vbTextCompare) <> 0 Then
        Exit Function
    End If
    
    Dim lngVersion As Long
    lngVersion = CLng(GetNodeAttr(oRoot, "VersionID", -1))
    
    If lngVersion = -1 Then
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
    
    oVersions.Add oProcessDef, lngVersion
    
    XMLVersion = True
    Exit Function
Err_Handler:
    Stop
    Resume 0
End Function

Public Function FileDeleteVersion(FileName As String, oProcessVersion As ProcessVersion)
    Dim oDoc As MSXML2.DOMDocument
    Set oDoc = GetDoc(FileName)
    Dim oRoot As MSXML2.IXMLDOMNode
    Set oRoot = GetVersionRoot(oDoc.firstChild)
    Dim oNode As MSXML2.IXMLDOMNode
    Dim oNVersions As IXMLDOMNodeList
    Set oNVersions = oRoot.childNodes
    Do
        Set oNode = oNVersions.nextNode
        If oNode Is Nothing Then Exit Do
        If CLng(GetNodeAttr(oNode, "VersionID", "-1")) = oProcessVersion.version Then
            oRoot.removeChild oNode
            Exit Do
        End If
    Loop
    oDoc.save FileName
    FileDeleteVersion = True
End Function

'/ updates the process definition in the XML file, adds a new revision
Public Function FileSaveRevisionXML(FileName As String, oProcessVersion As ProcessVersion) As Boolean
    
End Function

'/ saves the process definition to an XML file
Public Function FileSaveXML(FileName As String, oVersions As Versions, oProcessDef As ProcessDef) As Boolean
    
    Dim oProcessVersion As ProcessVersion
    Set oProcessVersion = oVersions.Add(oProcessDef)
    
    '/ now have our version number
    
    Dim oRoot As MSXML2.IXMLDOMNode
    
    Dim oDoc As MSXML2.DOMDocument
    Set oDoc = GetDoc(FileName)
    Set oRoot = GetVersionRoot(oDoc.firstChild)
    Dim oNode As MSXML2.IXMLDOMNode
    Set oNode = XMLNode(oRoot, "ProcessVersion")
    oRoot.appendChild oNode
    XMLAttr oNode, "VersionID", oProcessVersion.version
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
    XMLAttr oRoot, "Version", mcstrXMLVersion
        
    oRoot.appendChild XMLNode(oRoot, "ProcessVersions")
    Set GetDoc = oRoot.ownerDocument
End Function

Private Function GetVersionRoot(oRoot As IXMLDOMNode) As IXMLDOMNode
    Dim oNode As IXMLDOMNode
    If oRoot.nodeName <> "ACGWFDNative" Then
        Exit Function
    End If
    For Each oNode In oRoot.childNodes
        If StrComp(oNode.nodeName, "ProcessVersions", vbTextCompare) = 0 Then
            Set GetVersionRoot = oNode
            Exit Function
        End If
    Next
    
End Function
    
