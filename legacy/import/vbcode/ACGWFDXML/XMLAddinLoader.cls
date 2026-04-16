VERSION 1.0 CLASS
BEGIN
  MultiUse = -1  'True
  Persistable = 0  'NotPersistable
  DataBindingBehavior = 0  'vbNone
  DataSourceBehavior  = 0  'vbNone
  MTSTransactionMode  = 0  'NotAnMTSObject
END
Attribute VB_Name = "XMLAddinLoader"
Attribute VB_GlobalNameSpace = False
Attribute VB_Creatable = True
Attribute VB_PredeclaredId = False
Attribute VB_Exposed = True
Option Explicit

Public Function loadAddins(Path As String) As Collection
    '# scan the path for addin templates
    On Error GoTo Err_Handler
    Dim oScanPath As ScanPath
    Dim lngCount As Long
    Dim fLoadOK As Boolean
    Dim oAddins As New Collection
    
    Set oScanPath = New ScanPath
    oScanPath.StartScan Path, ".xml"
    
    Do Until oScanPath.FileList.Count = 0
        loadAddin oScanPath.FileList(1), oAddins
        oScanPath.FileList.Remove 1
    Loop
    
    Set loadAddins = oAddins
    Exit Function
Err_Handler:
    stackError Err, Me, "loadAddins"
End Function

Private Sub loadAddin(FileName As String, oAddins As Collection)
    On Error GoTo Err_Handler
    Dim oDoc As MSXML2.DOMDocument
    Dim oRoot As MSXML2.IXMLDOMNode
    
    Set oDoc = New MSXML2.DOMDocument
    
    oDoc.Load FileName
    
    Set oRoot = getRealNode(oDoc.firstChild)
    
    If StrComp(oRoot.nodeName, "ACGWFD.Addins", vbTextCompare) <> 0 Then
        Exit Sub
    End If
    
    processAddin oRoot, oAddins
    Exit Sub
Err_Handler:
    stackError Err, Me, "loadAddin"
End Sub

Private Sub processAddin(oRoot As MSXML2.IXMLDOMNode, oAddins As Collection)
    On Error GoTo Err_Handler
    Dim oAddin As Addin
    Dim n As IXMLDOMNode
    For Each n In oRoot.childNodes
        If StrComp(n.nodeName, "Addin", vbTextCompare) = 0 Then
            Set oAddin = New Addin
            oAddin.ClassName = GetNodeAttr(n, "classname")
            oAddin.MenuName = GetNodeAttr(n, "menuname")
            oAddins.Add oAddin
        End If
    Next
    Exit Sub
Err_Handler:
    stackError Err, Me, "processAddin"
    
End Sub

